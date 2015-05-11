
from time import time
import socket
import struct
import json

CODE_DISCOVER = 0x00
CODE_RESPONSE_DISCOVER = 0x01


class UpnpDiscoverSocket(object):
    def __init__(self, logger, callback, ipaddr="255.255.255.255", port=3310):
        self.logger = logger
        self.callback = callback
        self.dist = (ipaddr, port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM,
                                  socket.IPPROTO_UDP)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self._fileno = self.sock.fileno()

        self.discover_payload = struct.pack('<4s16sh', b"FLUX",
                                            b"\x00" * 16, CODE_DISCOVER)
        self.last_poke = 0

    def on_read(self):
        buf, remote = self.sock.recvfrom(4096)

        try:
            code, status = struct.unpack("<BB", buf[:2])
            payload = json.loads(buf[2:-1].decode("utf8"))

            if code == CODE_RESPONSE_DISCOVER:
                payload["from_lan"] = True
                self.callback(payload, "lan")
                
        except Exception as e:
            self.logger.debug("Unpack message error: %s" % e)

    def poke(self):
        t = time()
        if t - self.last_poke > 0.3:
            self.sock.sendto(self.discover_payload, self.dist)
            self.last_poke = t

    def fileno(self):
        return self._fileno

