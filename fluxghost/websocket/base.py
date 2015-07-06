
from select import select
from io import BytesIO
import logging
import os

from fluxghost.utils.websocket import WebSocketHandler, ST_NORMAL, \
    ST_GOING_AWAY, ST_INVALID_PAYLOAD

SIMULATE = "flux_simulate" in os.environ
logger = logging.getLogger("WS.BASE")


class WebSocketBase(WebSocketHandler):
    POOL_TIME = 30.0

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
        self.close(ST_INVALID_PAYLOAD, error)

    def on_read(self):
        self.do_recv()

    def on_loop(self):
        pass


class WebsocketBinaryHelperMixin(object):
    _binary_helper = None

    def has_binary_helper(self):
        return self._binary_helper is not None

    def set_binary_helper(self, helper):
        self._binary_helper = helper

    def on_binary_message(self, buf):
        try:
            if self._binary_helper:
                if self._binary_helper.feed(buf) == True:
                    self._binary_helper = None
            else:
                raise RuntimeError("BAD_PROTOCOL", "no binary accept")
        except RuntimeError as e:
            logger.error(e)
            self.send_fatal(e.args[0])


class BinaryUploadHelper(object):
    def __init__(self, length, callback, *args, **kwargs):
        self.length = length
        self.callback = callback
        self.buf = BytesIO()
        self.buffered = 0

        self.args = args
        self.kwargs = kwargs

    def feed(self, buf):
        l = self.buf.write(buf)
        self.buffered += l

        if self.buffered < self.length:
            return False
        elif self.buffered == self.length:
            self.callback(self.buf.getvalue(), *self.args, **self.kwargs)
            return True
        else:
            raise RuntimeError("BAD_LENGTH", "recive too many binary data ("
                               "should be %i but get %i" %
                               (self.length, self.buffered))
