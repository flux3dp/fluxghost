
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
    @classmethod
    def match_route(klass, path):
        return True if re.match("control/[0-9A-Z]{25}", path) else False

    POOL_TIME = 1.0

    def __init__(self, *args, **kw):
        WebSocketBase.__init__(self, *args, **kw)

        # self.POOL_TIME = 1.0
        self.serial = self.path[-25:]

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

    def _discover(self, serial):
        task = UpnpTask(self.serial)
        self.ipaddr = task.remote_addrs[0][0]

        return task

    def _conn_callback(self, *args):
        logger.debug("CONNECTING")
        self.send_text("connecting")
        return True

    def on_binary_message(self, buf):
        self.conn.send(buf)

    def on_text_message(self, message):
        if message.startswith("upload "):
            pass
        self.conn.send(message.encode())

    def on_robot_recv(self, buf):
        if buf:
            self.send_text(buf.decode("utf8"))
        else:
            self.close()

    def on_loop(self):
        pass
