
import logging
import shlex
import json

from fluxclient.robot import connect_robot
from fluxclient.upnp.task import UpnpTask

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
STAGE_CALL_ROBOT = '{"status": "connecting", "stage": "call_robot"}'
STAGE_CONNECTED = '{"status": "connected"}'
STAGE_TIMEOUT = '{"status": "error", "error": "TIMEOUT"}'

DEVICE_CACHE = {}


class WebsocketControlBase(WebSocketBase):
    robot = None
    simple_mapping = None
    cmd_mapping = None

    def __init__(self, *args, serial):
        WebSocketBase.__init__(self, *args)
        self.serial = serial

        self.send_text(STAGE_DISCOVER)
        task = self._discover(self.serial)

        try:
            logger.debug("AUTH")
            self.send_text(STAGE_DISCOVER)
            task.require_auth()

            logger.debug("REQUIRE ROBOT")
            self.send_text(STAGE_DISCOVER)

            try:
                task.require_robot()
            except RuntimeError as err:
                if err.args[0] != "ALREADY_RUNNING":
                    raise

            self.robot = connect_robot((self.ipaddr, 23811),
                                       server_key=task.pubkey,
                                       conn_callback=self._conn_callback)

        except TimeoutError:
            self.send_error("TIMEOUT")
            self.close()
            raise

        except RuntimeError as err:
            self.send_error(err.args[0])
            self.close()
            raise

        self.send_text(STAGE_CONNECTED)

    def on_closed(self):
        if self.robot:
            self.robot.close()
            self.robot = None
        self.simple_mapping = None
        self.cmd_mapping = None

    def _conn_callback(self, *args):
        self.send_text(STAGE_CALL_ROBOT)
        return True

    def _discover(self, serial):
        if serial in DEVICE_CACHE:
            try:
                cache = DEVICE_CACHE[serial]
                task = UpnpTask(self.serial, ipaddr=cache[0], pubkey=cache[1],
                                lookup_timeout=4.0)
            except RuntimeError as e:
                task = UpnpTask(self.serial)
        else:
            task = UpnpTask(self.serial)

        DEVICE_CACHE[serial] = (task.remote_addrs[0][0], task.pubkey)
        self.ipaddr = task.remote_addrs[0][0]
        return task


class WebsocketControl(WebsocketControlBase):
    binary_sock = None
    raw_sock = None

    def __init__(self, *args, serial):
        WebsocketControlBase.__init__(self, *args, serial=serial)
        self.set_hooks()

    def set_hooks(self):
        self.simple_mapping = {
            "start": self.robot.start_play,
            "pause": self.robot.pause_play,
            "resume": self.robot.resume_play,
            "abort": self.robot.abort_play,
            "report": self.robot.report_play,
            "quit": self.robot.quit_task,

            "scan": self.robot.begin_scan,
            "scan_backward": self.robot.scan_backward,
            "scan_next": self.robot.scan_next,
            "kick": self.robot.kick,

            "maintain": self.robot.begin_maintain,
            "home": self.robot.maintain_home,
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
            "update_fw": self.update_fw,
            "oneshot": self.oneshot,
            "scanimages": self.scanimages,
            "raw": self.begin_raw,

            "eadj": self.maintain_eadj
        }

    def on_binary_message(self, buf):
        if self.binary_sock:
            self.binary_sent += self.binary_sock.send(buf)
            if self.binary_sent < self.binary_length:
                pass
            elif self.binary_sent == self.binary_length:
                resp = self.robot.get_resp().decode("ascii", "ignore")
                if resp == "ok":
                    self.send_text('{"status": "ok"}')
                else:
                    errargs = resp.split(" ")
                    self.send_error(*(errargs[1:]))
            else:
                self.send_error("NOT_MATCH", "binary data length error")
                self.close()
        else:
            self.text_send("Can not accept binary data")
            self.close()

    def on_text_message(self, message):
        if message == "over_my_dead_body":
            import tempfile
            import os
            import gc
            fn = os.path.join(tempfile.gettempdir(), "over_my_dead_body.dump")
            with open(fn, "w") as f:
                for o in gc.get_objects():
                    f.write(repr(o) + "\n")
            self.send_text("ok " + fn)
            return

        if self.raw_sock:
            self.on_raw_message(message)
            return

        args = shlex.split(message, " ")
        cmd = args.pop(0)

        try:
            if cmd in self.simple_mapping:
                self.simple_cmd(self.simple_mapping[cmd], *args)
            elif cmd in self.cmd_mapping:
                func_ptr = self.cmd_mapping[cmd]
                func_ptr(*args)
            else:
                logger.error("Unknow Command: %s" % message)
                self.send_error("UNKNOW_COMMAND", "ws")

        except RuntimeError as e:
            logger.debug("RuntimeError%s" % repr(e.args))
            self.send_error(*e.args)

        except Exception as e:
            logger.exception("Unknow Error")
            self.send_error("UNKNOW_ERROR", repr(e.__class__))

    def simple_cmd(self, func, *args):
        try:
            self.send_text('{"status":"%s"}' % func(*args))
        except RuntimeError as e:
            self.send_error(*e.args)
        except Exception as e:
            logger.exception("Unknow Error")
            self.send_error("UNKNOW_ERROR", repr(e.__class__))

    def position(self):
        try:
            location = self.robot.position()
            self.send_text('{"status": "position", "location": "%s"}' %
                           location)
        except RuntimeError as e:
            self.send_error(*e.args)
        except Exception as e:
            logger.exception("Unknow Error")
            self.send_error("UNKNOW_ERROR", repr(e.__class__))

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

            self.send_text('{"status": "ok", "directories": %s, "files": '
                           '%s}' % (json.dumps(dirs), json.dumps(files)))
        else:
            self.send_text('{"status": "ok", "directories": '
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

    def upload_file(self, mimetype, size, uploadto="#"):
        #TODO
        self.binary_sock = self.robot.begin_upload(int(size))
        self.binary_length = int(size)
        self.binary_sent = 0
        self.send_text('{"status":"continue"}')

    def update_fw(self, size):
        self.binary_sock = self.robot.begin_upload(int(size), cmd="update_fw")
        self.binary_length = int(size)
        self.binary_sent = 0
        self.send_text('{"status":"continue"}')

    def maintain_eadj(self, *args):
        def callback(nav):
            self.send_text("Mainboard info: %s", nav)
        self.robot_obj.maintain_eadj(navigate_callback=callback)
        self.send_text("ok")

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

    def begin_raw(self):
        self.raw_sock = RawSock(self.robot.raw_mode(), self)
        self.rlist.append(self.raw_sock)
        self.send_ok()

    def on_raw_message(self, message):
        if message == "quit":
            self.rlist.remove(self.raw_sock)
            self.raw_sock = None
            self.robot.quit_raw_mode()
            self.send_ok()
        else:
            self.raw_sock.sock.send(message.encode() + b"\n")


class RawSock(object):
    def __init__(self, sock, ws):
        self.sock = sock
        self.ws = ws

    def fileno(self):
        return self.sock.fileno()

    def on_read(self):
        self.ws.send_text(self.sock.recv(128).decode("ascii", "ignore"))
