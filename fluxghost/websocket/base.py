
from select import select
import logging

from fluxghost.utils.websocket import WebSocketHandler, STATUS

logger = logging.getLogger("WS.BASE")


class WebSocketBase(WebSocketHandler):
    POOL_TIME = 30.0
    STATUS = STATUS

    @classmethod
    def match_route(klass, path):
        return False

    def __init__(self, request, client, server, path):
        WebSocketHandler.__init__(self, request, client, server)
        self.path = path
        self.rlist = [self]

    def serve_forever(self):
        try:
            while self.running:
                rl = select(self.rlist, (), (), self.POOL_TIME)[0]
                for r in rl:
                    r.on_read()

                self.on_loop()
        except Exception:
            logger.exception("Unhandle exception")
        finally:
            self.request.close()

    def send_fatal(self, error):
        self.send_text('{"status": "fatal", "error": "%s"}' % error)
        self.close(STATUS.INVALID_PAYLOAD, error)

    def on_read(self):
        self.doRecv()

    def on_loop(self):
        pass