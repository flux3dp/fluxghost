
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

class AsyncRawSock(object):
    def __init__(self, rawsock, callback):
        self.callback = callback
        self.rawsock = rawsock

    def send(self, buf):
        self.rawsock.send(buf)

    def fileno(self):
        return self.rawsock.fileno()

    def on_read(self):
        buf = self.rawsock.recv(4096)
        self.callback(buf.decode("utf8", "ignore"))


class WebsocketControl(WebSocketBase):
    raw_sock = None
    POOL_TIME = 1.0

    def __init__(self, *args, serial):
        WebSocketBase.__init__(self, *args)

        # self.POOL_TIME = 1.0
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

    def _discover(self, serial):
        task = UpnpTask(self.serial)
        self.ipaddr = task.remote_addrs[0][0]

        return task

    def _conn_callback(self, *args):
        logger.debug("CONNECTING")
        self.send_text("connecting")
        return True

    def on_binary_message(self, buf):
        #TODO
        self.conn.send(buf)

    def on_text_message(self, message):
        try:
            if self.raw_sock:
                self.raw_mode_handler(message)
            else:
                if message == "raw":
                    self.raw_sock = AsyncRawSock(self.robot.raw_mode(),
                                                 self.send_text)
                    self.rlist.append(self.raw_sock)
                    self.send_text("continue")
                else:
                    self.send_text("UNKNOW")
            # #TODO
            # self.conn.send(message.encode())
        except RuntimeError as err:
            logger.debug("Error: %s" % err)
            self.send_text("error " + err.args[0])

    def raw_mode_handler(self, message):
        if message == "quit":
            self.raw_sock.send(b"quit")
            self.raw_sock.on_read()
            self.rlist.remove(self.raw_sock)
            self.raw_sock = None
        else:
            if message.endswith("\n"):
                self.raw_sock.send(message.encode())
            else:
                self.raw_sock.send(message.encode() + b"\n")

    def on_robot_recv(self, buf):
        if buf:
            self.send_text(buf.decode("utf8"))
        else:
            self.close()

    def on_loop(self):
        pass
