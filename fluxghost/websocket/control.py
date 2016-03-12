
from errno import EPIPE, EHOSTDOWN, errorcode
from uuid import UUID
import logging
import socket
import shlex
from io import BytesIO
from os import environ

from fluxclient.utils.version import StrictVersion
from fluxclient.fcode.g_to_f import GcodeToFcode
from fluxclient.upnp.task import UpnpTask
from fluxclient.robot import connect_robot
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
STAGE_ROBOT_CONNECTING = '{"status": "connecting", "stage": "connecting"}'
STAGE_CONNECTED = '{"status": "connected"}'
STAGE_TIMEOUT = '{"status": "error", "error": "TIMEOUT"}'


class WebsocketControlBase(WebSocketBase):
    binary_handler = None
    cmd_mapping = None
    robot = None

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
        except OSError as err:
            error_no = err.args[0]
            if error_no == EHOSTDOWN:
                self.send_fatal("DISCONNECTED")
            else:
                self.send_fatal("UNKNOWN_ERROR",
                                errorcode.get(error_no, error_no))
            raise
        except RuntimeError as err:
            self.send_fatal(err.args[0], )
            raise

        self.remote_version = task.remote_version
        self.send_text(STAGE_CONNECTED)

    def on_binary_message(self, buf):
        if self.binary_handler:
            self.binary_handler(buf)
        else:
            self.send_fatal("PROTOCOL_ERROR", "Can not accept binary data")

    def simple_binary_transfer(self, mimetype, size, cmd, upload_to=None):
        bin_sock = self.robot.begin_upload(mimetype, int(size),
                                           cmd=cmd, upload_to=upload_to)
        upload_meta = {'sent': 0}

        def binary_handler(buf):
            bin_sock.send(buf)
            sent = upload_meta['sent'] = upload_meta['sent'] + len(buf)
            self.send_json(status="uploading", sent=sent)
            if sent < size:
                pass
            elif sent == size:
                self.binary_handler = None

                resp = self.robot.get_resp().decode("ascii", "ignore")
                if resp == "ok":
                    self.send_ok()
                else:
                    errargs = resp.split(" ")
                    self.send_error(*(errargs[1:]))
            else:
                self.send_fatal("NOT_MATCH", "binary data length error")

        self.binary_handler = binary_handler
        self.send_continue()

    def simple_binary_receiver(self, size, continue_cb):
        swap = BytesIO()
        upload_meta = {'sent': 0}

        def binary_handler(buf):
            swap.write(buf)
            sent = upload_meta['sent'] = upload_meta['sent'] + len(buf)

            if sent < size:
                pass
            elif sent == size:
                self.binary_handler = None
                continue_cb(swap)
            else:
                self.send_fatal("NOT_MATCH", "binary data length error")

        self.binary_handler = binary_handler
        self.send_continue()

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
    raw_sock = None

    def __init__(self, *args, **kw):
        try:
            WebsocketControlBase.__init__(self, *args, **kw)
            self.set_hooks()
        except RuntimeError:
            pass

    def fast_wrapper(self, func, cmd=None):
        def wrapper(*args, **kw):
            try:
                func(*args, **kw)
                if cmd:
                    self.send_text('{"status":"ok", "cmd": "%s"}' % cmd)
                else:
                    self.send_text('{"status":"ok"}')
            except RuntimeError as e:
                self.send_error(*e.args)
            except Exception as e:
                logger.exception("Unknow Error")
                self.send_error("UNKNOW_ERROR", repr(e.__class__))
        return wrapper

    def set_hooks(self):
        if self.remote_version < StrictVersion("1.0b13"):
            logger.warn("Remote version is too old, allow update fw only")
            self.cmd_mapping = {
                "update_fw": self.update_fw,
            }
            return

        self.cmd_mapping = {
            # deprecated
            "start": self.fast_wrapper(self.robot.start_play),
            # deprecated
            "pause": self.fast_wrapper(self.robot.pause_play),
            # deprecated
            "resume": self.fast_wrapper(self.robot.resume_play),
            # deprecated
            "abort": self.fast_wrapper(self.robot.abort_play),
            # deprecated
            "quit": self.fast_wrapper(self.robot.quit_play),
            # deprecated
            "position": self.position,
            # deprecated
            "ls": self.list_file,
            # deprecated
            "select": self.select_file,
            # deprecated
            "mkdir": self.mkdir,
            # deprecated
            "rmdir": self.rmdir,
            # deprecated
            "rmfile": self.rmfile,
            # deprecated
            "cpfile": self.cpfile,
            # deprecated
            "fileinfo": self.fileinfo,

            "upload": self.upload_file,
            "update_fw": self.update_fw,
            "update_mbfw": self.update_mbfw,

            "report": self.report_play,
            "kick": self.fast_wrapper(self.robot.kick, cmd="kick"),

            "file": {
                "ls": self.list_file,
                "mkdir": self.mkdir,
                "rmdir": self.rmdir,
                "rmfile": self.rmfile,
                "cpfile": self.cpfile,
                "info": self.fileinfo,
                "md5": self.filemd5,
                "download": self.download,
            },

            "maintain": {
                "load_filament": self.maintain_load_filament,
                "unload_filament": self.maintain_unload_filament,
                "calibrating": self.maintain_calibrating,
                "zprobe": self.maintain_zprobe,
                "headinfo": self.maintain_headinfo,
                "home": self.fast_wrapper(self.robot.maintain_home),
                "update_hbfw": self.maintain_update_hbfw
            },

            "config": {
                "set": self.config_set,
                "get": self.config_get,
                "del": self.config_del
            },

            "play": {
                "select": self.select_file,
                "start": self.fast_wrapper(self.robot.start_play),
                "info": self.play_info,
                "report": self.report_play,
                "pause": self.fast_wrapper(self.robot.pause_play),
                "resume": self.fast_wrapper(self.robot.resume_play),
                "abort": self.fast_wrapper(self.robot.abort_play),
                "quit": self.fast_wrapper(self.robot.quit_play)
            },

            "scan": {
                "backward": self.robot.scan_backward,
                "forward": self.robot.scan_next,
                "oneshot": self.oneshot,
                "scanimages": self.scanimages,
            },

            "task": {
                "maintain": self.task_begin_maintain,
                "scan": self.task_begin_scan,
                "raw": self.task_begin_raw,
                "quit": self.task_quit,
            }
        }

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
            if self.invoke_command(self.cmd_mapping, args):
                pass
            else:
                logger.warn("Unknow Command: %s" % message)
                self.send_error("UNKNOWN_COMMAND", "LEVEL: websocket")

        except RuntimeError as e:
            logger.debug("RuntimeError%s" % repr(e.args))
            self.send_error(*e.args)

        except (TimeoutError, ConnectionResetError,  # noqa
                socket.timeout, ) as e:
            from fluxclient.robot.v0002 import FluxRobotV0002
            import sys
            _, _, t = sys.exc_info()
            while t.tb_next:
                t = t.tb_next
                if "self" in t.tb_frame.f_locals:
                    if isinstance(t.tb_frame.f_locals["self"], FluxRobotV0002):
                        self.send_fatal("TIMEOUT", repr(e.args))
                        return
            self.send_error("UNKNOWN_ERROR2", repr(e.__class__))

        except socket.error as e:
            if e.args[0] == EPIPE:
                self.send_fatal("DISCONNECTED", repr(e.__class__))
            else:
                logger.exception("Unknow socket error")
                self.send_fatal("UNKNOWN_ERROR", repr(e.__class__))

        except Exception as e:
            logger.exception("Unknow error while process text")
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
            logger.exception("Command error")
            self.send_error("UNKNOWN_ERROR", repr(e.__class__))

    def position(self):
        try:
            location = self.robot.position()
            self.send_text('{"status": "position", "location": "%s"}' %
                           location)
        except RuntimeError as e:
            self.send_error(*e.args)

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

            dirs.sort()
            files.sort()
            self.send_json(status="ok", cmd="ls", path=location,
                           directories=dirs, files=files)
        else:
            self.send_json(status="ok", cmd="ls", path="",
                           directories=["SD", "USB"], files=[])

    def select_file(self, file):
        entry, path = file.split("/", 1)
        self.robot.select_file(entry, path)
        self.send_json({"status": "ok", "cmd": "select", "path": file})

    def fileinfo(self, file):
        entry, path = file.split("/", 1)
        info, binary = self.robot.fileinfo(entry, path)
        if binary:
            self.send_json(status="binary", mimetype=binary[0][0],
                           size=len(binary[0][1]))
            self.send_binary(binary[0][1])

        info["status"] = "ok"
        self.send_json(info)

    def filemd5(self, file):
        entry, path = file.split("/", 1)
        hash = self.robot.md5(entry, path)
        self.send_json(status="ok", cmd="md5", file=file, md5=hash)

    def mkdir(self, file):
        if file.startswith("SD/"):
            self.robot.mkdir("SD", file[3:])
            self.send_json(status="ok", cmd="mkdir", path=file)
        else:
            self.send_text('{"status": "error", "error": "NOT_SUPPORT"}')

    def rmdir(self, file):
        if file.startswith("SD/"):
            self.robot.rmdir("SD", file[3:])
            self.send_json(status="ok", cmd="rmdir", path=file)
        else:
            self.send_text('{"status": "error", "error": "NOT_SUPPORT"}')

    def rmfile(self, file):
        if file.startswith("SD/"):
            self.robot.rmfile("SD", file[3:])
            self.send_json(status="ok", cmd="rmfile", path=file)
        else:
            self.send_text('{"status": "error", "error": "NOT_SUPPORT"}')

    def download(self, file):
        logger.debug(file)

        report = lambda left, size: self.send_json(status="continue", left=left, size=size)
        entry, path = file.split("/", 1)
        buf = BytesIO()
        mimetype = self.robot.download_file(entry, path, buf, report)
        if mimetype:
            self.send_json(status="binary", mimetype=mimetype, size=buf.truncate())
            self.send_binary(buf.getvalue())

    def cpfile(self, source, target):
        params = source.split("/", 1) + target.split("/", 1)
        self.robot.cpfile(*params)
        self.send_json(status="ok", cmd="cpfile", source=source,
                       target=target)

    def upload_file(self, mimetype, ssize, upload_to="#"):
        if upload_to == "#":
            pass
        elif upload_to.startswith("SD/"):
            upload_to = "SD " + upload_to[3:]
        elif upload_to.startswith("USB/"):
            upload_to = "USB " + upload_to[4:]

        size = int(ssize)
        if mimetype == "text/gcode":
            if upload_to.endswith('.gcode'):
                upload_to = upload_to[:-5] + 'fc'

            def upload_callback(swap):
                gcode_content = swap.getvalue().decode("ascii", "ignore").split('\n')

                if gcode_content[1] == ';Laser Gcode':
                    head_type = "LASER"
                elif gcode_content[1] == ';Pen Gcode':
                    head_type = "N/A"
                elif gcode_content[0].startswith('; generated by Slic3r'):
                    head_type = "EXTRUDER"
                else:
                    head_type = "EXTRUDER"

                fcode_output = BytesIO()
                g2f = GcodeToFcode(head_type=head_type, ext_metadata={"CORRECTION": "A"})

                g2f.process(gcode_content, fcode_output)
                ########## fake code  ########################
                if environ.get("flux_debug") == '1':
                    with open('output.fc', 'wb') as ff:
                        ff.write(fcode_output.getvalue())
                ##################################################

                fcode_len = fcode_output.truncate()
                remote_sent = 0

                fcode_output.seek(0)
                sock = self.robot.begin_upload('application/fcode',
                                               fcode_len,
                                               cmd="file upload",
                                               upload_to=upload_to)
                self.send_json(status="uploading", sent=0,
                               amount=fcode_len)
                while remote_sent < fcode_len:
                    remote_sent += sock.send(fcode_output.read(4096))
                    self.send_json(status="uploading", sent=remote_sent)

                resp = self.robot.get_resp().decode("ascii", "ignore")
                if resp == "ok":
                    self.send_ok()
                else:
                    errargs = resp.split(" ")
                    self.send_error(*(errargs[1:]))

            self.simple_binary_receiver(size, upload_callback)

        elif mimetype == "application/fcode":
            self.simple_binary_transfer(mimetype, size, cmd="file upload",
                                        upload_to=upload_to)

        else:
            self.send_text('{"status":"error", "error": "FCODE_ONLY"}')
            return

    def update_fw(self, mimetype, ssize):
        self.simple_binary_transfer(mimetype, int(ssize), "update_fw")

    def update_mbfw(self, mimetype, ssize):
        self.simple_binary_transfer(mimetype, int(ssize), "update_mbfw")

    def maintain_update_hbfw(self, mimetype, ssize):
        size = int(ssize)

        def update_cb(swap):
            def nav_cb(nav):
                args = nav.split(" ")
                if args[1] == "UPLOADING":
                    self.send_json(status="uploading", sent=int(args[2]))
                elif args[1] == "WRITE":
                    self.send_json(status="update_hbfw", stage="WRITE",
                                   written=size - int(args[2]))
                else:
                    self.send_json(status="update_hbfw", stage=args[1])
                logger.debug("--> %s", nav)
            size = swap.truncate()
            swap.seek(0)

            try:
                self.robot.maintain_update_hbfw(mimetype, swap, size, nav_cb)
                self.send_ok()
            except RuntimeError as e:
                self.send_error(*e.args)
            except Exception as e:
                self.send_fatal("UNKNOWN_ERROR", e.args)

        self.simple_binary_receiver(size, update_cb)

    def task_begin_scan(self):
        self.robot.begin_scan()
        self.send_text('{"status":"ok", "task": "scan"}')

    def task_begin_maintain(self):
        self.robot.begin_maintain()
        self.send_text('{"status":"ok", "task": "maintain"}')

    def task_begin_raw(self):
        self.raw_sock = RawSock(self.robot.raw_mode(), self)
        self.rlist.append(self.raw_sock)
        self.send_text('{"status":"ok", "task": "raw"}')

    def task_quit(self):
        self.robot.quit_task()
        self.send_text('{"status":"ok", "task": ""}')

    def maintain_calibrating(self, *args):
        def callback(nav):
            self.send_text("DEBUG: %s" % nav)
        if "clean" in args:
            ret = self.robot.maintain_calibrating(navigate_callback=callback,
                                                  clean=True)
        else:
            ret = self.robot.maintain_calibrating(navigate_callback=callback)
        self.send_json(status="ok", data=ret, error=(max(*ret) - min(*ret)))

    def maintain_zprobe(self, *args):
        def callback(nav):
            self.send_text("DEBUG: %s" % nav)

        if len(args) > 0:
            ret = self.robot.maintain_hadj(navigate_callback=callback,
                                           manual_h=float(args[0]))
        else:
            ret = self.robot.maintain_hadj(navigate_callback=callback)

        self.send_json(status="ok", data=ret)

    def maintain_load_filament(self, index, temp):
        def nav(n):
            self.send_json(status="loading", nav=n)
        self.robot.maintain_load_filament(int(index), float(temp), nav)
        self.send_ok()

    def maintain_unload_filament(self, index, temp):
        def nav(n):
            self.send_json(status="unloading", nav=n)
        self.robot.maintain_unload_filament(int(index), float(temp), nav)
        self.send_ok()

    def maintain_headinfo(self):
        info = self.robot.maintain_headinfo()
        info["cmd"] = "headinfo"
        info["status"] = "ok"
        self.send_json(info)

    def report_play(self):
        data = self.robot.report_play()
        data["status"] = "ok"
        data["cmd"] = "report"
        self.send_json(data)

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
        self.send_json(metadata)

        for mime, buf in images:
            self.send_binary_begin(mime, len(buf))
            self.send_binary(buf)
        self.send_ok()

    def config_set(self, key, value):
        self.robot.config_set(key, value)
        self.send_json(status="ok", cmd="set", key=key)
        self.send_ok()

    def config_get(self, key):
        value = self.robot.config_get(key)
        self.send_json(status="ok", cmd="get", key=key, value=value)

    def config_del(self, key):
        self.robot.config_del(key)
        self.send_json(status="ok", cmd="del", key=key)

    def on_raw_message(self, message):
        if message == "quit" or message == "task quit":
            self.rlist.remove(self.raw_sock)
            self.raw_sock = None
            self.robot.quit_raw_mode()
            self.send_text('{"status": "ok", "task": ""}')
        else:
            self.raw_sock.sock.send(message.encode() + b"\n")


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
