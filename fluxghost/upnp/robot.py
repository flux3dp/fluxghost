
import socket

from fluxclient import encryptor as E


def create_robot(ipaddr, callback, logger):
    s = socket.socket()
    s.connect(ipaddr)

    buf = s.recv(8, socket.MSG_WAITALL)
    if buf[:4] != b"FLUX":
        raise Exception("Bad magic number")
    elif bif[4:] == b"0002":
        return Robot0002(sock, callback, logger)
    else:
        raise Exception("Can not support version %s" % buf[4:].decode())


class Robot0002(object):
    def __init__(self, sock, callback, logger):
        self.callback = callback

        buf = s.recv(4096)
        sign, randbytes = buf[:-128], buf[-128:]
        rsakey = E.get_or_create_keyobj()
        buf = E.get_access_id(rsakey, binary=True) + E.sign(rsakey, randbytes)
        s.send(buf)

        status = s.recv(16).rstrip(b"\x00").decode()
        if status != "OK":
            raise RuntimeError(status)

    def fileno(self):
        return self.sock.fileno()

    def send(self, buf):
        self.sock.send(buf)

    def on_read(self):
        buf = self.sock.recv(4096)
        self.callback(buf)

