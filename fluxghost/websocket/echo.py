
from datetime import datetime
import logging
import struct

from .base import WebSocketBase, STATUS

logger = logging.getLogger("WS.ECHO")

"""
This is a simple ECHO websocket for testing only

Javascript Example:

ws = new WebSocket("ws://localhost:8080/ws/echo");
ws.onmessage = function(v) { console.log(v.data);}
ws.onclose = function(v) { console.log("CONNECTION CLOSED, code=" + v.code +
    "; reason=" + v.reason); }

ws.onopen = function() {
    ws.send("Say Hello")
    ws.send("die BYEBYE")
}
"""


class WebsocketEcho(WebSocketBase):
    POOL_TIME = 30.0
    enable_timer = False

    def onMessage(self, message, is_binary):
        if message == "time on":
            logger.debug("Timer ON")
            self.enable_timer = True
            self.POOL_TIME = 5.0
        elif message == "time off":
            logger.debug("Timer OFF")
            self.enable_timer = False
            self.POOL_TIME = 30.0
        elif message.startswith("die "):
            logger.debug("Recive %s" % message)
            close_msg = message.split(" ", 1)[-1]
            self.close(STATUS.GOING_AWAY, close_msg)
        else:
            logger.debug("ECHO %s" % message)
            self.send(message, is_binary)

    def onClose(self, message):
        code = struct.unpack(">H", message[:2])[0]
        logger.debug("CLOSE: %i, %s" % (code, message[2:].decode("utf8")))
        super(WebsocketEcho, self).onClose(message)

    def on_loop(self):
        if self.enable_timer:
            self.send("Current Time: %s" % datetime.now())
