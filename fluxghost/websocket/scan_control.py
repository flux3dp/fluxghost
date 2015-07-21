
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
import math
import os

from fluxclient.scanner.tools import read_pcd
from fluxclient.scanner import scan_settings, image_to_pc

from .base import WebSocketBase
from .control import WebsocketControlBase

SIMULATE_IMG_FILE = os.path.join(os.path.dirname(__file__),
                                 "..", "assets", "miku_q.png")
SIMULATE_IMG_MIME = "image/png"
L = logging.getLogger("WS.3DSCAN-CTRL")

scan_settings.img_width = 640
scan_settings.img_height = 480


class Websocket3DScanControl(WebsocketControlBase):
    ready = False
    steps = 200
    current_step = 0
    proc = None

    def __init__(self, *args, serial):
        WebsocketControlBase.__init__(self, *args, serial=serial)

        try:
            position = self.robot.position()

            if position == "CommandTask":
                ret = self.robot.begin_scan()
                if ret == "ok":
                    self.send_text('{"status": "ready"}')
                    self.ready = True
                else:
                    self.send_error('DEVICE_ERROR', ret)
            else:
                self.send_error('DEVICE_BUSY', position)

        except RuntimeError as err:
            if err.args[0] == "RESOURCE_BUSY":
                self.send_error('DEVICE_BUSY', err.args[-1])
            else:
                self.send_error('DEVICE_ERROR', err.args[0])

    def on_binary_message(self, buf):
        self.text_send("Protocol error")
        self.close()

    def on_text_message(self, message):
        if message == "take_control":
            self.take_control()

        elif message == "image":
            self.fetch_image()

        elif message.startswith("resolution "):
            s_step = message.split(" ", 1)[-1]
            self.steps = int(s_step, 10)
            self.current_step = 0
            self.proc = image_to_pc.image_to_pc()
            self.send_ok(str(self.steps))

        elif message == "scan":
            self.scan()

        elif message == "quit":
            if self.robot.position() == "ScanTask":
                self.robot.quit_task()

            self.send_text("bye")
            self.close()

        else:
            self.send_error("UNKNOW_COMMAND", message)

    def take_control(self):
        if self.ready:
            self.send_error("ALREADY_READY")

        try:
            position = self.robot.position()
            if position != "CommandTask":
                ret = self.robot.quit_task()
                if ret != "ok":
                    self.send_error("DEVICE_ERROR", ret)
                    return
        except RuntimeError as err:
            if err.args[0] == "RESOURCE_BUSY":
                ret = self.robot.kick()
                if ret != "ok":
                    self.send_error("DEVICE_ERROR", ret)
                    return
            else:
                self.send_error("DEVICE_ERROR", err.args[0])
                return

        ret = self.robot.begin_scan()
        if ret == "ok":
            self.send_text('{"status": "ready"}')
            self.ready = True
        else:
            self.send_error("DEVICE_ERROR %s", ret)

    def fetch_image(self):
        if not self.ready:
            self.send_error("NOT_READY")
            return

        images = self.robot.oneshot()
        for mime, buf in images:
            self.send_binary_begin(mime, len(buf))
            self.send_binary(buf)
        self.send_ok()

    def scan(self):
        if not self.ready:
            self.send_error("NOT_READY")
            return

        if not self.proc:
            self.send_error("BAD_PARAMS", "resolution")
            return

        L.debug('Do scan')
        ir, il, io = self.robot.scanimages()
        left_r, right_r = self.proc.feed(io[1], il[1], ir[1],
                                         self.current_step)

        self.current_step += 1
        self.send_text('{"status": "chunk", "left": %d, "right": %d}' %
                       (len(left_r), len(right_r)))
        self.send_binary(b''.join(left_r))
        self.send_binary(b''.join(right_r))
        self.robot.scan_next()
        self.send_ok()


class SimulateWebsocket3DScanControl(WebSocketBase):
    steps = 200
    current_step = 0
    mode = 'cube'

    def __init__(self, *args, serial):
        WebSocketBase.__init__(self, *args)
        with open(SIMULATE_IMG_FILE, "rb") as f:
            self.image_buf = f.read()

        self.serial = serial
        self.send_text('{"status": "connected"}')
        self.send_text('{"status": "ready"}')

    def on_text_message(self, message):
        if message == "image":
            self.send_binary_begin(SIMULATE_IMG_MIME, len(self.image_buf))
            self.send_binary(self.image_buf)
            self.send_ok()

        elif message == "mode ":
            mode = message.split(" ", 1)
            if mode not in ['cube', 'pcd', 'hemisphere']:
                self.send_error("BAD_PARAMS", info=mode)
            else:
                self.mode = mode
                self.send_ok(info=mode)

        elif message.startswith("resolution "):
            s_step = message.split(" ", 1)[-1]
            self.steps = int(s_step, 10)
            self.current_step = 0
            self.send_ok(str(self.steps))

        elif message == "scan":
            self.scan()

        elif message == "quit":
            self.send_text("bye")
            self.close()

        else:
            self.send_error("UNKNOW_COMMAND", message)

    def scan(self):
        if self.mode == 'pcd':
            if self.current_step > 0:
                self.send_text('{"status": "chunk", "left": 0, "right": 0}')
                self.send_ok()
                return

            self.current_step += 1
            PCD_LOCATION = os.path.join(os.path.dirname(__file__), "..",
                                        "assets")

            pc_L = read_pcd(PCD_LOCATION + '/LL.pcd')
            self.send_text('{"status": "chunk", "left": %d, "right": 0}' %
                           len(pc_L))
            buf = []
            for p in pc_L:
                buf.append(struct.pack('<' + 'f' * 6, p[0], p[1], p[2],
                           p[3] / 255., p[4] / 255., p[5] / 255.))
            buf = b''.join(buf)
            self.send_binary(buf)

            pc_R = read_pcd(PCD_LOCATION + '/RR.pcd')
            self.send_text('{"status": "chunk", "left": 0, "right": %d}' %
                           len(pc_R))
            buf = []
            for p in pc_R:
                buf.append(struct.pack('<' + 'f' * 6, p[0], p[1], p[2],
                           p[3] / 255., p[4] / 255., p[5] / 255.))
            buf = b''.join(buf)
            self.send_binary(buf)
            self.send_ok()

        elif self.mode == 'hemisphere':
            i = self.current_step
            self.current_step += 1

            step = math.pi * 2 / self.steps
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
            self.send_ok()

        elif self.mode == 'cube':
            i = self.current_step
            self.current_step += 1

            buf = []
            self.send_text('{"status": "chunk", "left": 1250, "right": 1250}')
            for j in range(-50, 50, 2):
                for k in range(-50, 50, 2):
                    x, y, z = map(float, [j, k, i / 2.])
                    buf.append(struct.pack("<ffffff", x, y, z, 0.0, 0.0, 0.0))
            buf = b"".join(buf)
            self.send_binary(buf)
            self.send_ok()
