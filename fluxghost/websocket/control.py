
from select import select
from time import time, sleep
import logging
import json
import re

from fluxclient.upnp_task import UpnpTask
from fluxclient import encryptor as E

from fluxghost.upnp.robot import RobotSocket
from .base import WebSocketBase

logger = logging.getLogger("WS.CONTROL")


"""
Control printer

Javascript Example:

ws = new WebSocket("ws://localhost:8080/ws/control/RLFPAPI7E8KXG64KG5NOWWY3T");
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

        # TODO
        connected = False
        for i in range(3): # retry 3 times
            if connected:
                break

            try:
                self._connect()
                connected = True
            except ConnectionRefusedError as err:
                logger.debug("Robot connection refused, retry (%i)" % i)
            except RuntimeError as err:
                self.send_text("error %s" % err.args[0])

        if not connected:
            self.send_text("timeout")
            self.close()

        self.send_text("connected")

    def _discover(self, serial):
        task = UpnpTask(self.serial)
        self.ipaddr = task.remote_addrs[0][0]

        return task

    def _connect(self):
        # TODO
        sleep(0.5)
        logger.debug("CONNECTING")
        self.send_text("connecting")
        self.conn = RobotSocket(self.on_robot_recv, (self.ipaddr, 23811),
                                logger)
        self.rlist.append(self.conn)

    def onMessage(self, message, is_binary):
        if is_binary:
            self.on_recv_binary(message)
        else:
            self.on_recv_text(message)

    def on_recv_binary(self, buf):
        self.conn.send(buf)

    def on_recv_text(self, message):
        logger.debug("WebSocket Send: %s" % message)
        self.conn.send(message.encode())

    def on_robot_recv(self, buf):
        if buf:
            self.send_text(buf.decode("utf8"))
        else:
            self.close()

    def on_loop(self):
        pass
