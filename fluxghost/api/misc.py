
from time import time
from io import BytesIO


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
