from select import select
from io import BytesIO
from time import time
import logging
import json
import os

from fluxghost.utils.websocket import WebSocketHandler, ST_NORMAL, \
    ST_GOING_AWAY, ST_INVALID_PAYLOAD, WebsocketError

SIMULATE = "flux_simulate" in os.environ
logger = logging.getLogger("WS.BASE")


class WebSocketBase(WebSocketHandler):
    POOL_TIME = 30.0
    TIMEOUT = 600
    timer = 0

    def __init__(self, request, client, server, path):
        WebSocketHandler.__init__(self, request, client, server)
        self.path = path
        self.rlist = [self]
        self.timer = time()

    def serve_forever(self):
        try:
            while self.running:
                rl = select(self.rlist, (), (), self.POOL_TIME)[0]
                for r in rl:
                    r.on_read()

                self.check_ttl()
                self.on_loop()
        except WebsocketError as e:
            logger.info("%s", e)
        except Exception:
            logger.exception("Unhandle exception")
        finally:
            self.request.close()
            self.on_closed()

    def send_ok(self, info=None):
        if info:
            self.send_text('{"status": "ok", "info": "%s"}' % info)
        else:
            self.send_text('{"status": "ok"}')

    def send_json(self, payload=None, **kw_payload):
        if payload:
            self.send_text(json.dumps(payload))
        else:
            self.send_text(json.dumps(kw_payload))

    def send_continue(self):
        self.send_text('{"status": "continue"}')

    def send_binary_begin(self, mime, length):
        self.send_text('{"status": "binary", "length": %i, "mime": "%s"}' %
                       (length, mime))

    def send_error(self, errcode, info=None, *args):
        if info:
            self.send_text(
                '{"status": "error", "error": "%s", "info":"%s"}' % (errcode,
                                                                     info))
        else:
            self.send_text('{"status": "error", "error": "%s"}' % errcode)

    def send_fatal(self, error, suberror=None):
        self.send_text('{"status": "fatal", "error": "%s", "info": "%s"}' %
                       (error, suberror))
        self.close(ST_INVALID_PAYLOAD, error)

    def send_progress(self, message, percentage):
        self.send_text('{"status": "computing", "message": "%s", "percentage": %.2f}' % (message, percentage))

    def send_warning(self, message):
        self.send_text('{"status": "warning", "message" : "%s"}' % (message))

    def on_read(self):
        self.timer = time()
        self.do_recv()

    def check_ttl(self):
        t = self.timer + self.TIMEOUT

        if not self.running:
            return

        if self._is_closing and t < time():
            self.close_directly()

        elif t < time():
            self.close(message="error TIMEOUT")

    def on_loop(self):
        pass

    def on_closed(self):
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
                if self._binary_helper.feed(buf) is True:
                    self._binary_helper = None
            else:
                raise RuntimeError("BAD_PROTOCOL", "no binary accept")
        except RuntimeError as e:
            logger.error(e)
            self.send_fatal(e.args[0])

    def on_loop(self):
        if self._binary_helper:
            if time() - self._binary_helper.last_update > 20:
                self.send_fatal('binary receive timeout')
                raise RuntimeError('binary receive timeout')


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
                               (self.length, self.buffered), "recive too many binary data ("
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
                    self.cmd_mapping[cmd][0](params, *self.cmd_mapping[cmd][1:])
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
