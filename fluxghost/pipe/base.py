
from select import select
import logging

from fluxghost.api.api_base import ApiBase

logger = logging.getLogger("PIPE.BASE")
__all__ = ["PipeBase"]


class PipeBase(ApiBase):
    POOL_TIME = 30.0

    def __init__(self, stdin, stdout, options):
        self.stdin, self.stdout = stdin, stdout
        self.options = options
        self.rlist = [self]
        self.running = True

        self._recv_buf = b""
        self._recv_len = None
        self._recv_bin = None

    def fileno(self):
        return self.stdin.fileno()

    def serve_forever(self):
        try:
            ApiBase.serve_forever(self)
        except KeyboardInterrupt:
            self.close()
        except Exception:
            logger.exception("Unhandle exception")
        finally:
            pass

    def _serve_forever(self):
        while self.running:
            rl = select(self.rlist, (), (), self.POOL_TIME)[0]
            for r in rl:
                r.on_read()

            self.on_loop()

    def on_read(self):
        if self._recv_len is None:
            buf = self.stdin.read(8 - len(self._recv_buf))
            if len(buf):
                self._recv_buf += buf
                if len(buf) == 8:
                    self._recv_len = int(self._recv_buf[1:], 16)
                    tp = self._recv_buf[0]
                    if tp == 116:
                        self._recv_bin = False
                    elif tp == 98:
                        self._recv_bin = True
                    else:
                        logger.error("Unknow message type: %s", tp)
                        self.close()
                    self._recv_buf = b""
                    self.on_read_body()
            else:
                self.close()
        else:
            self.on_read_body()

    def _on_read_body(self):
        buf = self.stdin.read(self._recv_len - len(self._recv_buf))
        if len(buf):
            self._recv_buf += buf
            if len(buf) == self._recv_len:
                self._on_message(self._recv_buf, self._recv_bin)
            else:
                return
        else:
            self.close()

    def _on_message(self, buf, is_binary):
        try:
            if is_binary:
                self.on_binary_message(self._recv_buf)
            else:
                self.on_text_message(self._recv_buf.decode("utf8"))
        except Exception:
            pass

    def close(self):
        self.running = False
        self.stdout.close()
        self.stdin.close()

    def _on_loop(self):
        pass

    def on_loop(self):
        pass

    def send_text(self, text):
        buf = text.encode()
        self.stdout.write(("t%07x" % len(buf)).encode())
        self.stdout.write(buf)
        self.stdout.flush()

    def send_binary(self, buf):
        self.stdout.write(("t%07x" % len(buf)).encode())
        self.stdout.write(buf)
        self.stdout.flush()
