
from time import time
from io import BytesIO
import logging

logger = logging.getLogger("API.MISC")


class BinaryHelperMixin(object):
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
                    logger.exception("Received message: %s" % (message))
                    raise ValueError('Undefined Command %s' % (cmd))
            else:
                logger.exception("Received Message: %s" % (message))
                raise RuntimeError("PROTOCOL_ERROR", "under uploading mode")

        except ValueError:
            logger.exception("Received Message: %s" % (message))
            self.send_json(status='Error', message='BAD_PARAM_TYPE')

        except RuntimeError as e:
            logger.exception("Received Message: %s" % (message))
            self.send_fatal(e.args[0])


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
