
from select import select
import logging
import json

logger = logging.getLogger("PROTOCOL.BASE")


class ApiBase(object):
    POOL_TIME = 30.0
    # Should implement
    # * rlist = [io1, io2, ...]
    # * running = True or False
    # * def on_loop()

    def serve_forever(self):
        try:
            while self.running:
                rl = select(self.rlist, (), (), self.POOL_TIME)[0]
                for r in rl:
                    r.on_read()

                self.on_loop()
        finally:
            self.on_closed()

    def send_ok(self, **kw):
        if kw:
            kw["status"] = "ok"
            self.send_text(json.dumps(kw))
        else:
            self.send_text('{"status": "ok"}')

    def send_json(self, payload=None, **kw_payload):
        if payload:
            self.send_text(json.dumps(payload))
        else:
            self.send_text(json.dumps(kw_payload))

    def send_continue(self):
        self.send_text('{"status": "continue"}')

    def send_binary_buffer(self, mimetype, buffer):
        size = len(buffer)
        self.send_json(status="binary", mimetype=mimetype, size=size)
        view = memoryview(buffer)
        sent = 0
        while sent < size:
            self.send_binary(view[sent:sent + 4016])
            sent += 4016

    def send_binary_begin(self, mime, length):
        self.send_text('{"status": "binary", "length": %i, "mime": "%s"}' %
                       (length, mime))

    def send_error(self, errcode, info=None, symbol=None, *args):
        if symbol:
            self.send_json(status="error", error=symbol[0], symbol=symbol)
        elif info:
            self.send_text(
                '{"status": "error", "error": "%s", "info":"%s"}' % (errcode,
                                                                     info))
        else:
            self.send_text('{"status": "error", "error": "%s"}' % errcode)

    def send_fatal(self, *args):
        if args:
            if len(args) > 1:
                self.send_json(status="fatal", symbol=args, error=args[0],
                               info=args[1])
            else:
                self.send_json(status="fatal", symbol=args, error=args[0])
        else:
            self.send_json(status="fatal", error="NOT_GIVEN", symbol=[])

    def send_progress(self, message, percentage):
        self.send_text('{"status": "computing", "message": "%s", "percentage":'
                       ' %.2f}' % (message, percentage))

    def send_warning(self, message):
        self.send_text('{"status": "warning", "message" : "%s"}' % (message))
