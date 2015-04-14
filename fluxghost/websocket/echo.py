
from datetime import datetime
import logging


from .base import WebSocketBase

logger = logging.getLogger("WS.ECHO")


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
        else:
            logger.debug("ECHO %s" % message)
            self.send(message, is_binary)

    def on_loop(self):
        if self.enable_timer:
            self.send("Current Time: %s" % datetime.now())
