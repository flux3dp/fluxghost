
"""
Control printer

Javascript Example:

ws = new WebSocket(
    "ws://localhost:8000/ws/3d-scan-control/RLFPAPI7E8KXG64KG5NOWWY3T");
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
from fluxclient.scanner.tools import read_pcd

# <<<<<<<< Fake Code
IMG_FILE = os.path.join(os.path.dirname(__file__),
                        "..", "assets", "miku_q.png")
# >>>>>>>>

logger = logging.getLogger("WS.3DSCAN-CTRL")


class Websocket3DScanControl(WebSocketBase):
    def __init__(self, *args, serial):
        WebSocketBase.__init__(self, *args)
        self.serial = serial
        self.send_text("connecting")
        self.send_text("connecting")
        self.send_text("connected")

    def on_text_message(self, message):
        if message == "image":
            self._fetch_image()
        elif message == "start":
            self._scan()

        elif message == "quit":
            self.send_text("bye")
            self.close()

    def _fetch_image(self):
        with open(IMG_FILE, "rb") as f:
            buf = f.read()
            self.send_text("ok %i" % len(buf))
            self.send_binary(buf)
            self.send_text("finished")

    def _scan(self):
        logger.debug('scanning')

        self.send_text("ok")
        # <<<<<<<< Fake Code: read in a pcd file
        # PCD_LOCATION = os.path.join(os.path.dirname(__file__), "..", "assets")

        # pc_L = read_pcd(PCD_LOCATION + '/LL.pcd')
        # self.send_text('{"status": "chunk", "left": %d, "right": 0}' % len(pc_L))
        # buf = []
        # for p in pc_L:
        #     buf.append(struct.pack('<' + 'f' * 6, p[0], p[1], p[2], p[3] / 255., p[4] / 255., p[5] / 255.))
        # buf = b''.join(buf)
        # self.send_binary(buf)

        # pc_R = read_pcd(PCD_LOCATION + '/RR.pcd')
        # self.send_text('{"status": "chunk", "left": 0, "right": %d}' % len(pc_R))
        # buf = []
        # for p in pc_R:
        #     buf.append(struct.pack('<' + 'f' * 6, p[0], p[1], p[2], p[3] / 255., p[4] / 255., p[5] / 255.))
        # buf = b''.join(buf)
        # self.send_binary(buf)

        # >>>>>>>> Fake Code: generate a hemisphere
        import math
        STEPS = 200

        step = math.pi * 2 / STEPS
        for i in range(STEPS):
            r = step * i

            try:
                c = math.cos(r) / math.sin(r)
            except ZeroDivisionError:
                c = float("INF")

            self.send_text('{"status": "chunk", "left": 100, "right": 100}')

            buf = b""
            for iz in range(-100, 100):
                z = iz / 200
                x = math.sqrt((1 - (z ** 2)) / (1 + c ** 2))

                if step > math.pi / 2 and step < (math.pi * 3 / 4):
                    x = -x

                y = x * c if c != float("INF") else 1

                buf += struct.pack("<ffffff", x, y, z, 1.0, 1.0, 1.0)
            self.send_binary(buf)

        # >>>>>>>> Fake Code

        self.send_text("finished")
