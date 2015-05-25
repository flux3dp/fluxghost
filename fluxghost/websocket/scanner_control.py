
"""
Control printer

Javascript Example:

ws = new WebSocket(
    "ws://localhost:8000/ws/3d-scanner-control/RLFPAPI7E8KXG64KG5NOWWY3T");
ws.onmessage = function(v) { console.log(v.data);}
ws.onclose = function(v) { console.log("CONNECTION CLOSED, code=" + v.code +
    "; reason=" + v.reason); }

// After recive connected...
ws.send("image")
"""


import logging
import struct
import os
import re

from .base import WebSocketBase, ST_NORMAL

# <<<<<<<< Fake Code
IMG_FILE = os.path.join(os.path.dirname(__file__),
                        "..", "assets", "miku_q.png")
# >>>>>>>>

logger = logging.getLogger("WS.3DSCAN-CTRL")


class Websocket3DScannerController(WebSocketBase):
    @classmethod
    def match_route(klass, path):
        return re.match("3d-scanner-control/[0-9A-Z]{25}", path) is not None

    def __init__(self, *args, **kw):
        WebSocketBase.__init__(self, *args, **kw)
        self.serial = self.path[-25:]
        self.send_text("connecting")
        self.send_text("connecting")
        self.send_text("connected")

    def on_text_message(self, message):
        if message == "image":
            with open(IMG_FILE, "rb") as f:
                buf = f.read()
                self.send_text("ok %i" % len(buf))
                self.send_binary(buf)
        elif message == "start":
            self.send_text("ok")
            self._scan()
            self.send_text("finished")

        elif message == "quit":
            self.send_text("bye")
            self.close()

    def _scan(self):
        # <<<<<<<< Fake Code
        import math
        STEPS = 400

        step = math.pi * 2 / STEPS
        for i in range(STEPS):
            r = step * i

            try:
                c = math.cos(r) / math.sin(r)
            except ZeroDivisionError:
                c = float("INF")

            self.send_text("chunk 200 200")

            buf = b""
            for iz in range(-200, 200):
                z = iz / 200
                x = math.sqrt((1 - (z**2)) / (1 + c**2))

                if step > math.pi / 2 and step < (math.pi * 3 / 4):
                    x = -x

                y = x * c if c != float("INF") else 1

                buf += struct.pack("<fffBBB", x, y, z, 255, 255, 255)
            self.send_binary(buf)
        # >>>>>>>> Fake Code