
from time import time
import logging

from fluxghost.api import ApiBase
from fluxghost.utils.websocket import WebSocketHandler, WebsocketError, \
    ST_UNEXPECTED_CONDITION

logger = logging.getLogger("WS.BASE")

__all__ = ["WebSocketBase", ]


class WebSocketBase(WebSocketHandler, ApiBase):
    TIMEOUT = 600
    timer = 0

    def __init__(self, request, client, server, path):
        WebSocketHandler.__init__(self, request, client, server)
        self.path = path
        self.rlist = [self]
        self.timer = time()

    def serve_forever(self):
        try:
            ApiBase.serve_forever(self)
        except WebsocketError as e:
            if self._is_closing:
                logger.debug("WebsocketError: %s", e)
            else:
                logger.exception("Unhandle websocket exception")
        except Exception:
            logger.exception("Unhandle exception")
        finally:
            self.request.close()

    def send_fatal(self, *args):
        ApiBase.send_fatal(self, *args)
        self.close(error=True, message="error %s" % args[0])

    def on_read(self):
        try:
            self.timer = time()
            self.do_recv()
        except WebsocketError:
            self.close_directly()

    def _on_loop(self):
        self.check_ttl()

    def check_ttl(self):
        if hasattr(self, "_binary_helper") and self._binary_helper:
            if time() - self._binary_helper.last_update > 60:
                self.send_fatal('TIMEOUT', 'WAITING_BINARY')

        t = self.timer + self.TIMEOUT

        if not self.running:
            return

        if self._is_closing and t < time():
            self.close_directly()

        elif t < time():
            self.close(error=True, message="error TIMEOUT")

    def close(self, error=False, message=None):
        if error:
            WebSocketHandler.close(self, code=ST_UNEXPECTED_CONDITION,
                                   message=message)
        else:
            WebSocketHandler.close(self)
