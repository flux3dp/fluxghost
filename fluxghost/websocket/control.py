
import logging

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


class WebsocketControlBase(WebSocketBase):
    def __init__(self, *args, serial):
        WebSocketBase.__init__(self, *args)
        self.serial = serial

        self.send_text(STAGE_DISCOVER)
        task = self._discover(self.serial)

        try:
            logger.debug("AUTH")
            self.send_text(STAGE_DISCOVER)
            task.require_auth()

        except RuntimeError as e:
            self.send_text("error %s" % e.args[0])
            self.close()
            raise

        try:
            logger.debug("REQUIRE ROBOT")
            self.send_text(STAGE_DISCOVER)
            resp = task.require_robot()

            if not resp:
                self.send_text("timeout")
                self.close()
                raise RuntimeError("TIMEOUT")
        except RuntimeError as err:
            if err.args[0] != "ALREADY_RUNNING":
                self.send_text("timeout")
                self.close()
                raise

        self.robot = connect_robot((self.ipaddr, 23811), server_key=None,
                                   conn_callback=self._conn_callback)

        self.send_text(STAGE_CONNECTED)

    def _conn_callback(self, *args):
        self.send_text(STAGE_CALL_ROBOT)
        return True

    def _discover(self, serial):
        task = UpnpTask(self.serial)
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
            "select": self.robot.select_file,
            "start": self.robot.start_play,
            "pause": self.robot.pause_play,
            "resume": self.robot.resume_play,
            "abort": self.robot.abort_play,
            "report": self.robot.report_play,
            "position": self.robot.position,
            "quit": self.robot.quit_task,

            "scan": self.robot.begin_scan,
            "scan_forword": self.robot.scan_forword,
            "scan_next": self.robot.scan_next,

            "maintain": self.robot.begin_maintain,
            "home": self.robot.maintain_home,
        }

        self.cmd_mapping = {
            "ls": self.list_file,
            "upload": self.upload_file,
            "oneshot": self.oneshot,
            "scanimages": self.scanimages,
            "raw": self.begin_raw,
        }

    def on_binary_message(self, buf):
        if self.binary_sock:
            self.binary_sent += self.binary_sock.send(buf)
            if self.binary_sent < self.binary_length:
                pass
            elif self.binary_sent == self.binary_length:
                self.send_text(self.robot.get_resp().decode("ascii", "ignore"))
            else:
                self.send_text("error NOT_MATCH binary data length error")
                self.close()
        else:
            self.text_send("Can not accept binary data")
            self.close()

    def on_text_message(self, message):
        if self.raw_sock:
            self.on_raw_message(message)
            return

        args = message.split(" ", 1)
        cmd = args[0]

        try:
            if cmd in self.simple_mapping:
                self.simple_cmd(self.simple_mapping[cmd], *args[1:])
            elif cmd in self.cmd_mapping:
                func_ptr = self.cmd_mapping[cmd]
                func_ptr(*args[1:])
            else:
                self.send_text("UNKNOW_COMMAND ws")
                logger.error("Unknow Command: %s" % message)

        except RuntimeError as e:
            logger.error("RuntimeError%s" % repr(e.args))

    def simple_cmd(self, func, *args):
        try:
            self.send_text(func(*args))
        except RuntimeError as e:
            self.send_text("error %s" % " ".join(e.args))

    def list_file(self):
        try:
            for f in self.robot.list_file():
                self.send_text(f)
            self.send_text("ok")
        except RuntimeError as e:
            self.send_text("error %s" % " ".join(e.args))

    def upload_file(self, size):
        self.binary_sock = self.robot.begin_upload(int(size))
        self.binary_length = int(size)
        self.binary_sent = 0
        self.send_text("continue")

    def oneshot(self):
        images = self.robot.oneshot()
        for mime, buf in images:
            size = len(buf)
            self.send_text("binary %s %s" % (mime, size))
            view = memoryview(buf)
            sent = 0
            while sent < size:
                self.send_binary(view[sent:sent + 4016])
                sent += 4016
        self.send_text("ok")

    def scanimages(self):
        images = self.robot.scanimages()
        for mime, buf in images:
            size = len(buf)
            self.send_text("binary %s %s" % (mime, size))
            view = memoryview(buf)
            sent = 0
            while sent < size:
                self.send_binary(view[sent:sent + 4016])
                sent += 4016
        self.send_text("ok")

    def begin_raw(self):
        self.raw_sock = RawSock(self.robot.raw_mode(), self)
        self.rlist.append(self.raw_sock)
        self.send_text("ok")

    def on_raw_message(self, message):
        if message == "quit":
            self.raw_sock.sock.send("quit")
            self.raw_sock.on_read()
            self.raw_sock = None
        else:
            self.raw_sock.sock.send(message.encode() + b"\n")
    
    def on_loop(self):
        pass


class RawSock(object):
    def __init__(self, sock, ws):
        self.sock = sock
        self.ws = ws

    def fileno(self):
        return self.sock.fileno()

    def on_read(self):
        self.ws.send_text(self.sock.recv(128).decode("ascii", "ignore"))

