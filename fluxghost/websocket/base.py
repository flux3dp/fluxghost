
from io import BytesIO
from time import time
import logging
import os

from fluxghost.api import ApiBase
from fluxghost.utils.websocket import WebSocketHandler, WebsocketError, \
    ST_UNEXPECTED_CONDITION

SIMULATE = "flux_simulate" in os.environ
logger = logging.getLogger("WS.BASE")

__all__ = ["WebSocketBase", "SIMULATE", ]


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
        self.timer = time()
        self.do_recv()

    def _on_loop(self):
        self.check_ttl()

    def check_ttl(self):
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


class WebsocketBinaryHelperMixin(object):
    _binary_helper = None

    def has_binary_helper(self):
        return self._binary_helper is not None

    def set_binary_helper(self, helper):
        self._binary_helper = helper

    def on_binary_message(self, buf):
        try:
            if self._binary_helper:
                if self._binary_helper.feed(buf) is True:
                    self._binary_helper = None
            else:
                raise RuntimeError("BAD_PROTOCOL", "no binary accept")
        except RuntimeError as e:
            logger.error(e)
            self.send_fatal(e.args[0])

    def on_loop(self):
        if self._binary_helper:
            if time() - self._binary_helper.last_update > 60:
                self.send_fatal('TIMEOUT', 'WAITING_BINARY')
        self.check_ttl()


class BinaryUploadHelper(object):
    def __init__(self, length, callback, *args, **kwargs):
        self.length = length
        self.callback = callback
        self.buf = BytesIO()
        self.buffered = 0

        self.args = args
        self.kwargs = kwargs

        self.last_update = time()

    def feed(self, buf):
        l = self.buf.write(buf)
        self.buffered += l
        self.last_update = time()

        if self.buffered < self.length:
            return False
        elif self.buffered == self.length:
            self.callback(self.buf.getvalue(), *self.args, **self.kwargs)
            return True
        else:
            raise RuntimeError("BAD_LENGTH" + " recive too many binary data ("
                               "should be %i but get %i" %
                               (self.length, self.buffered),
                               "recive too many binary data ("
                               "should be %i but get %i" %
                               (self.length, self.buffered))


class OnTextMessageMixin(object):
    def on_text_message(self, message):
        try:
            if not self.has_binary_helper():
                message = message.rstrip().split(maxsplit=1)
                if len(message) == 1:
                    cmd = message[0]
                    params = ''
                else:
                    cmd = message[0]
                    params = message[1]

                if cmd in self.cmd_mapping:
                    self.cmd_mapping[cmd][0](params,
                                             *self.cmd_mapping[cmd][1:])
                else:
                    logger.exception("receive message: %s" % (message))
                    raise ValueError('Undefine command %s' % (cmd))
            else:
                logger.exception("receive message: %s" % (message))
                raise RuntimeError("PROTOCOL_ERROR", "under uploading mode")

        except ValueError:
            logger.exception("receive message: %s" % (message))
            self.send_fatal("BAD_PARAM_TYPE")

        except RuntimeError as e:
            logger.exception("receive message: %s" % (message))
            self.send_fatal(e.args[0])
