
from select import select
from time import time, sleep
import logging
import json
import re

from fluxclient.robot import connect_robot, RobotError
from fluxclient.upnp.task import UpnpTask
from fluxclient import encryptor as E

# from fluxghost.upnp.robot import RobotSocket
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


class WebsocketControl(WebSocketBase):
    POOL_TIME = 1.0
    binary_sock = None

    def __init__(self, *args, serial):
        WebSocketBase.__init__(self, *args)

        self.serial = serial

        try:
            logger.debug("DISCOVER")
            self.send_text("connecting")
            task = self._discover(self.serial)

            logger.debug("AUTH")
            self.send_text("connecting")
            auth_result = task.require_auth()

        except RuntimeError:
            self.send_text("timeout")
            self.close()
            raise

        if auth_result and auth_result.get("status") != "ok":
            self.send_text("no_auth")
            self.close()
            raise RuntimeError("NO AUTH")

        try:
            logger.debug("REQUIRE ROBOT")
            self.send_text("connecting")
            resp = task.require_robot()

            if not resp:
                self.send_text("timeout")
                self.close()
                raise RuntimeError("TIMEOUT")
        except RuntimeError as err:
            if err.args[0] != "ALREADY_RUNNING":
                self.send_text("timeout")
                self.close()

        self.robot = connect_robot((self.ipaddr, 23811), server_key=None,
                                   conn_callback=self._conn_callback)

        self.send_text("connected")
        self.set_hooks()

    def _discover(self, serial):
        task = UpnpTask(self.serial)
        self.ipaddr = task.remote_addrs[0][0]

        return task

    def _conn_callback(self, *args):
        logger.debug("CONNECTING")
        self.send_text("connecting")
        return True

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
            # "oneshot": self.oneshot,
            # "scanimages": self.scanimages,
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
        for f in self.robot.list_file():
            self.send_text(f)
        self.send_text("ok")

    def upload_file(self, size):
        self.binary_sock = self.robot.begin_upload(int(size))
        self.binary_length = int(size)
        self.binary_sent = 0
        self.send_text("continue")

    def on_loop(self):
        pass
