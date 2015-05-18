
import socket

from fluxclient import encryptor as E


class RobotSocket(object):
    def __init__(self, callback, ipaddr, logger):
        self.callback = callback

        self.sock = s = socket.socket()

        s.connect(ipaddr)
        buf = s.recv(4096)

        ver, sign, randbytes = buf[:8], buf[8:-128], buf[-128:]
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
