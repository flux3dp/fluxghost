
import logging


from .base import WebSocketBase

logger = logging.getLogger("WS.ECHO")


class WebsocketDiscover(WebSocketBase):
    POOL_TIME = 5.0

    def __init__(self, *args, **kw):
        WebSocketBase.__init__(self, *args, **kw)

    def onMessage(self, message, is_binary):
        logger.debug("ECHO %s" % message)
        self.send(message, is_binary)

    def on_loop(self):
        pass
