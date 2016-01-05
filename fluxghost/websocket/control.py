
from errno import EPIPE
from uuid import UUID
import logging
import socket
import shlex
import json
import io
from os import environ

from fluxclient.robot import connect_robot
from fluxclient.upnp.task import UpnpTask
from fluxclient.fcode.g_to_f import GcodeToFcode
from .base import WebSocketBase

logger = logging.getLogger("WS.CONTROL")


"""
Control printer

Javascript Example:

ws = new WebSocket("ws://localhost:8000/ws/control/RLFPAPI7E8KXG64KG5NOWWY3T");
ws.onmessage = function(v) { console.log(v.data);}
ws.onclose = function(v) { console.log("CONNECTION CLOSED, code=" + v.code +
    "; reason=" + v.reason); }

// After recive connected...
ws.send("ls")
"""


STAGE_DISCOVER = '{"status": "connecting", "stage": "discover"}'
STAGE_AUTH = '{"status": "connecting", "stage": "auth"}'
STAGE_ROBOT_INIT = '{"status": "connecting", "stage": "initial"}'
STAGE_ROBOT_LAUNGING = '{"status": "connecting", "stage": "launching"}'
STAGE_ROBOT_LAUNCHED = '{"status": "connecting", "stage": "launched"}'
STAGE_ROBOT_CONNECTING = '{"status": "connecting", "stage": "connecting"}'
STAGE_CONNECTED = '{"status": "connected"}'
STAGE_TIMEOUT = '{"status": "error", "error": "TIMEOUT"}'


class WebsocketControlBase(WebSocketBase):
    robot = None
    simple_mapping = None
    cmd_mapping = None

    def __init__(self, request, client, server, path, serial):
        WebSocketBase.__init__(self, request, client, server, path)
        self.uuid = UUID(hex=serial)

        self.send_text(STAGE_DISCOVER)
        logger.debug("DISCOVER")

        try:
            task = self._discover(self.uuid)
            self.send_text(STAGE_ROBOT_CONNECTING)
            self.robot = connect_robot((self.ipaddr, 23811),
                                       server_key=task.slave_key,
                                       conn_callback=self._conn_callback)
        except RuntimeError as err:
            self.send_fatal(err.args[0], )
            raise

        self.send_text(STAGE_CONNECTED)

    def _fix_auth_error(self, task):
        self.send_text(STAGE_DISCOVER)
        if task.timedelta < -15:
            logger.warn("Auth error, try fix time delta")
            old_td = task.timedelta
            task.reload_remote_profile(lookup_timeout=30.)
            if task.timedelta - old_td > 0.5:
                # Fix timedelta issue let's retry
                p = self.server.discover_devices.get(self.uuid)
                if p:
                    p["timedelta"] = task.timedelta
                    self.server.discover_devices[self.uuid] = p
                    return True
        return False

    def on_closed(self):
        if self.robot:
            self.robot.close()
            self.robot = None
        self.simple_mapping = None
        self.cmd_mapping = None

    def _disc_callback(self, *args):
        self.send_text(STAGE_DISCOVER)
        return True

    def _conn_callback(self, *args):
        self.send_text(STAGE_ROBOT_CONNECTING)
        return True

    def _discover(self, uuid):
        profile = self.server.discover_devices.get(uuid)
        if profile:
            task = UpnpTask(self.uuid, remote_profile=profile,
                            lookup_timeout=4.0)
        else:
            task = UpnpTask(self.uuid, lookup_callback=self._disc_callback)

        self.ipaddr = task.endpoint[0]
        return task


class WebsocketControl(WebsocketControlBase):
    binary_sock = None
    raw_sock = None
    convert = None

    def __init__(self, *args, **kw):
        try:
            WebsocketControlBase.__init__(self, *args, **kw)
            self.set_hooks()
        except RuntimeError:
            pass

    def fast_wrapper(self, func):
        def wrapper(*args, **kw):
            try:
                self.send_text('{"status":"%s"}' % func(*args, **kw))
            except RuntimeError as e:
                self.send_error(*e.args)
            except Exception as e:
                logger.exception("Unknow Error")
                self.send_error("UNKNOW_ERROR", repr(e.__class__))
        return wrapper

    def set_hooks(self):
        self.simple_mapping = {
            "start": self.robot.start_play,
            "pause": self.robot.pause_play,
            "resume": self.robot.resume_play,
            "abort": self.robot.abort_play,
            "quit": self.robot.quit_play,

            "scan": self.robot.begin_scan,
            "scan_backward": self.robot.scan_backward,
            "scan_next": self.robot.scan_next,
            "kick": self.robot.kick,

            "home": self.robot.maintain_home,

            "task": {
                "start": self.robot.start_play,
                "maintain": self.robot.begin_maintain,
                "scan": self.robot.begin_scan,
            }
        }

        self.cmd_mapping = {
            "position": self.position,

            "ls": self.list_file,
            "select": self.select_file,
            "mkdir": self.mkdir,
            "rmdir": self.rmdir,
            "rmfile": self.rmfile,
            "cpfile": self.cpfile,
            "fileinfo": self.fileinfo,
            "upload": self.upload_file,
            "upload_g": self.upload_file,
            "update_fw": self.update_fw,
            "update_mbfw": self.update_mbfw,
            "oneshot": self.oneshot,
            "scanimages": self.scanimages,
            "raw": self.begin_raw,

            "report": self.report_play,

            "maintain": {
                "load_filament": self.maintain_load_filament,
                "unload_filament": self.maintain_unload_filament,
                "calibrating": self.maintain_calibrating,
                "zprobe": self.maintain_zprobe,
                "headinfo": self.maintain_headinfo,
                "home": self.fast_wrapper(self.robot.maintain_home)
            },

            "config": {
                "set": self.config_set,
                "get": self.config_get,
                "del": self.config_del
            },

            "play": {
                "info": self.play_info,
                "report": self.report_play,
                "pause": self.fast_wrapper(self.robot.pause_play),
                "resume": self.fast_wrapper(self.robot.resume_play),
                "abort": self.fast_wrapper(self.robot.abort_play),
                "quit": self.fast_wrapper(self.robot.quit_play)
            },

            "task": {
                "quit": self.fast_wrapper(self.robot.quit_task)
            }
        }

    def on_binary_message(self, buf):
        if self.binary_sock or isinstance(self.convert, io.BytesIO):
            if isinstance(self.convert, io.BytesIO):
                self.binary_sent += self.convert.write(buf)
            else:
                self.binary_sent += self.binary_sock.send(buf)

            if self.binary_sent < self.binary_length:
                pass
            elif self.binary_sent == self.binary_length:
                if isinstance(self.convert, io.BytesIO):
                    f_buf = self.g_to_f()

                    # ############### fake code ################
                    if environ.get("flux_debug") == '1':
                        with open('tmp.fcode', 'wb') as f:
                            f.write(f_buf)
                    # #######################################

                    self.binary_sock = self.robot.begin_upload(
                        'application/fcode', len(f_buf),
                        cmd="file upload", uploadto=self.uploadto)
                    self.binary_sock.send(f_buf)
                    del self.uploadto
                    self.convert = None

                self.binary_sock = None

                resp = self.robot.get_resp().decode("ascii", "ignore")
                if resp == "ok":
                    self.send_text('{"status": "ok"}')
                else:
                    errargs = resp.split(" ")
                    self.send_error(*(errargs[1:]))
            else:
                self.binary_sock = None
                self.send_fatal("NOT_MATCH", "binary data length error")
        else:
            self.binary_sock = None
            self.send_fatal("PROTOCOL_ERROR", "Can not accept binary data")

    def invoke_command(self, ref, args, wrapper=None):
        if not args:
            return False

        cmd = args[0]
        if cmd in ref:
            obj = ref[cmd]
            if isinstance(obj, dict):
                return self.invoke_command(obj, args[1:], wrapper)
            else:
                if wrapper:
                    wrapper(obj, *args[1:])
                else:
                    obj(*args[1:])
                return True
        return False

    def on_text_message(self, message):
        if message == "ping":
            self.send_text('{"status": "pong"}')
            return

        if self.raw_sock:
            self.on_raw_message(message)
            return

        args = shlex.split(message)

        try:
            if self.invoke_command(self.simple_mapping, args,
                                   self.simple_cmd):
                pass
            elif self.invoke_command(self.cmd_mapping, args):
                pass
            else:
                logger.error("Unknow Command: %s" % message)
                self.send_error("UNKNOWN_COMMAND", "ws")

        except RuntimeError as e:
            logger.debug("RuntimeError%s" % repr(e.args))
            self.send_error(*e.args)

        except socket.error as e:
            if e.args[0] == EPIPE:
                self.send_fatal("DISCONNECTED", repr(e.__class__))
            else:
                logger.exception("Unknow Error")
                self.send_fatal("UNKNOWN_ERROR", repr(e.__class__))

        except Exception as e:
            logger.exception("Unknow Error")
            self.send_error("UNKNOWN_ERROR", repr(e.__class__))

    def simple_cmd(self, func, *args):
        try:
            ret = func(*args)
            if ret:
                self.send_text('{"status":"%s"}' % ret)
            else:
                self.send_text('{"status":"ok"}')
        except RuntimeError as e:
            self.send_error(*e.args)
        except Exception as e:
            logger.exception("Unknow Error")
            self.send_error("UNKNOWN_ERROR", repr(e.__class__))

    def position(self):
        try:
            location = self.robot.position()
            self.send_text('{"status": "position", "location": "%s"}' %
                           location)
        except RuntimeError as e:
            self.send_error(*e.args)
        except Exception as e:
            logger.exception("Unknow Error")
            self.send_error("UNKNOWN_ERROR", repr(e.__class__))

    def list_file(self, location=None):
        if location:
            params = location.split("/", 1)
            dirs = []
            files = []
            for is_dir, name in self.robot.list_files(*params):
                if is_dir:
                    dirs.append(name)
                else:
                    files.append(name)

            payload = {"status": "ok", "path": location, "directories": dirs,
                       "files": files}
            self.send_text(json.dumps(payload))
        else:
            self.send_text('{"status": "ok", "path": "", "directories": '
                           '["SD", "USB"], "files": []}')

    def select_file(self, file):
        entry, path = file.split("/", 1)
        self.robot.select_file(entry, path)
        self.send_text('{"status": "ok"}')

    def fileinfo(self, file):
        entry, path = file.split("/", 1)
        info, binary = self.robot.fileinfo(entry, path)
        if binary:
            self.send_text(json.dumps({
                "status": "binary", "mimetype": binary[0],
                "size": len(binary[1])
            }))
            self.send_binary(binary[1])

        info["status"] = "ok"
        self.send_text(json.dumps(info))

    def mkdir(self, file):
        if file.startswith("SD/"):
            self.simple_cmd(self.robot.mkdir, "SD", file[3:])
        else:
            self.send_text('{"status": "error", "error": "NOT_SUPPORT"}')

    def rmdir(self, file):
        if file.startswith("SD/"):
            self.simple_cmd(self.robot.rmdir, "SD", file[3:])
        else:
            self.send_text('{"status": "error", "error": "NOT_SUPPORT"}')

    def rmfile(self, file):
        if file.startswith("SD/"):
            self.simple_cmd(self.robot.rmfile, "SD", file[3:])
        else:
            self.send_text('{"status": "error", "error": "NOT_SUPPORT"}')

    def cpfile(self, args):
        if args.startswith("@"):
            source, target = args[1:].split("#")
        else:
            source, target = args.split("\x00")
        params = source.split("/", 1) + target.split("/", 1)
        self.simple_cmd(self.robot.cpfile, *params)

    def upload_file(self, mimetype, size, uploadto="#", convert='0'):
        if uploadto == "#":
            pass
        elif uploadto.startswith("SD/"):
            uploadto = "SD " + uploadto[3:]
        elif uploadto.startswith("USB/"):
            uploadto = "USB " + uploadto[4:]

        if mimetype == "text/gcode" and convert != '1':
            self.send_text('{"status":"error", "error": "FCODE_ONLY"}')
            return
        if mimetype == "text/gcode" and convert == '1':
            self.convert = io.BytesIO()
            if uploadto.endswith('.gcode'):
                uploadto = uploadto[:-5] + 'fc'
            self.uploadto = uploadto
        else:
            self.convert = None
            self.binary_sock = self.robot.begin_upload(mimetype, int(size),
                                                       cmd="file upload",
                                                       uploadto=uploadto)

        self.binary_length = int(size)
        self.binary_sent = 0
        self.send_text('{"status":"continue"}')

    def update_fw(self, mimetype, size):
        self.binary_sock = self.robot.begin_upload(mimetype, int(size),
                                                   cmd="update_fw")
        self.binary_length = int(size)
        self.binary_sent = 0
        self.send_text('{"status":"continue"}')

    def update_mbfw(self, mimetype, size):
        self.binary_sock = self.robot.begin_upload(mimetype, int(size),
                                                   cmd="update_mbfw")
        self.binary_length = int(size)
        self.binary_sent = 0
        self.send_text('{"status":"continue"}')

    def maintain_calibrating(self, *args):
        def callback(nav):
            self.send_text("DEBUG: %s" % nav)
        if "clean" in args:
            ret = self.robot.maintain_calibrating(navigate_callback=callback,
                                                  clean=True)
        else:
            ret = self.robot.maintain_calibrating(navigate_callback=callback)
        self.send_text(json.dumps({
            "status": "ok", "data": ret, "error": (max(*ret) - min(*ret))
        }))

    def maintain_zprobe(self, *args):
        def callback(nav):
            self.send_text("DEBUG: %s" % nav)

        if len(args) > 0:
            ret = self.robot.maintain_hadj(navigate_callback=callback,
                                           manual_h=float(args[0]))
        else:
            ret = self.robot.maintain_hadj(navigate_callback=callback)

        self.send_text(json.dumps({"status": "ok", "data": ret}))

    def maintain_load_filament(self, index, temp):
        def nav(n):
            self.send_text(json.dumps({"status": "loading", "nav": n}))
        self.robot.maintain_load_filament(int(index), float(temp), nav)
        self.send_ok()

    def maintain_unload_filament(self, index, temp):
        def nav(n):
            self.send_text(json.dumps({"status": "loading", "nav": n}))
        self.robot.maintain_unload_filament(int(index), float(temp), nav)
        self.send_ok()

    def maintain_headinfo(self):
        info = self.robot.maintain_headinfo()
        info["status"] = "headinfo"
        self.send_text(json.dumps(info))

    def report_play(self):
        # TODO
        data = self.robot.report_play()
        if isinstance(data, dict):
            data["status"] = "ok"
            data["cmd"] = "report"
            self.send_text(json.dumps(data))
        else:
            self.send_text(data)

    def oneshot(self):
        images = self.robot.oneshot()
        for mime, buf in images:
            size = len(buf)
            self.send_text('{"status": "binary", "mimetype": %s, '
                           '"size": %i}' % (mime, size))
            view = memoryview(buf)
            sent = 0
            while sent < size:
                self.send_binary(view[sent:sent + 4016])
                sent += 4016
        self.send_ok()

    def scanimages(self):
        images = self.robot.scanimages()
        for mime, buf in images:
            size = len(buf)
            self.send_text('{"status": "binary", "mimetype": %s, '
                           '"size": %i}' % (mime, size))
            view = memoryview(buf)
            sent = 0
            while sent < size:
                self.send_binary(view[sent:sent + 4016])
                sent += 4016
        self.send_ok()

    def play_info(self):
        metadata, images = self.robot.play_info()
        metadata["status"] = "playinfo"
        self.send_text(json.dumps(metadata))

        for mime, buf in images:
            self.send_binary_begin(mime, len(buf))
            self.send_binary(buf)
        self.send_ok()

    def config_set(self, key, value):
        self.robot.config_set(key, value)
        self.send_ok()

    def config_get(self, key):
        value = self.robot.config_get(key)
        if value:
            self.send_text("ok VAL %s" % value)
        else:
            self.send_text("ok EMPTY")

    def config_del(self, key):
        self.robot.config_del(key)
        self.send_ok()

    def begin_raw(self):
        self.raw_sock = RawSock(self.robot.raw_mode(), self)
        self.rlist.append(self.raw_sock)
        self.send_ok()

    def on_raw_message(self, message):
        if message == "quit" or message == "task quit":
            self.rlist.remove(self.raw_sock)
            self.raw_sock = None
            self.robot.quit_raw_mode()
            self.send_ok()
        else:
            self.raw_sock.sock.send(message.encode() + b"\n")

    def g_to_f(self):
        fcode_output = io.BytesIO()
        g2f = GcodeToFcode()
        g2f.process(self.convert.getvalue().decode().split('\n'),
                    fcode_output)
        self.convert = None
        return fcode_output.getvalue()


class RawSock(object):
    def __init__(self, sock, ws):
        self.sock = sock
        self.ws = ws

    def fileno(self):
        return self.sock.fileno()

    def on_read(self):
        buf = self.sock.recv(128)
        if buf:
            self.ws.send_text(buf.decode("ascii", "replace"))
        else:
            self.ws.rlist.remove(self)
            self.ws.send_fatal("DISCONNECTED")
