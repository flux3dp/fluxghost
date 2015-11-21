
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
import sys

from fluxclient.scanner.tools import read_pcd
from fluxclient.scanner import scan_settings, image_to_pc
from fluxclient.hw_profile import HW_PROFILE

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
        self.try_control()
        self.cab = None

    def on_binary_message(self, buf):
        self.text_send("Protocol error")
        self.close()

    def on_text_message(self, message):
        if message == "take_control":
            self.take_control()

        elif message == "retry":
            self.try_control()

        elif message == "image":
            self.fetch_image()

        elif message == "scan_check":
            self.scan_check()

        elif message.startswith("resolution "):

            s_step = message.split(maxsplit=1)[-1]
            self.steps = int(s_step, 10)  # should be 400 or 800
            if self.steps in HW_PROFILE['model-1']['step_setting']:
                self.robot.set_scanlen(HW_PROFILE['model-1']['step_setting'][self.steps][1])
            else:
                self.steps = 400  # this will cause frontend couldn't adjust the numbers of steps
                self.robot.set_scanlen(HW_PROFILE['model-1']['step_setting'][400][1])

            scan_settings.scan_step = self.steps
            self.current_step = 0
            self.proc = image_to_pc.image_to_pc()
            self.send_ok(str(self.steps))

        elif message == "scan":
            if self.cab is None:
                self.get_cab()
            self.scan()

        elif message == "quit":
            if self.robot.position() == "ScanTask":
                self.robot.quit_task()

            self.send_text("bye")
            self.close()

        else:
            self.send_error("UNKNOW_COMMAND", message)

    def try_control(self):
        if self.ready:
            self.send_error("ALREADY_READY")

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

    def scan_check(self):
        if not self.ready:
            self.send_error("NOT_READY")
            return

    def get_cab(self):
        self.cab = [float(i) for i in self.robot.get_calibrate().split()]

    def scan(self):
        if not self.ready:
            self.send_error("NOT_READY")
            return

        if not self.proc:
            self.send_error("BAD_PARAMS", "resolution")
            return

        L.debug('Do scan %d' % (self.current_step))

        # ###################
        # if self.current_step > 10:
        #     self.current_step += 1
        #     self.send_text('{"status": "chunk", "left": 0, "right": 0}')
        #     self.send_binary(b'')
        #     self.send_ok()
        #     return
        # ###################

        il, ir, io = self.robot.scanimages()
        left_r, right_r = self.proc.feed(io[1], il[1], ir[1], self.current_step, self.cab[0], self.cab[1])

        self.current_step += 1

        self.send_text('{"status": "chunk", "left": %d, "right": %d}' %
                       (len(left_r), len(right_r)))
        self.send_binary(b''.join(left_r + right_r))
        self.robot.scan_next()
        self.send_ok()


class SimulateWebsocket3DScanControl(WebSocketBase):
    steps = 200
    current_step = 0
    mode = 'box'

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
            mode = message.split(maxsplit=1)
            if mode not in ['cube', 'pcd', 'hemisphere', 'box']:
                self.send_error("BAD_PARAMS", info=mode)
            else:
                self.mode = mode
                self.send_ok(info=mode)

        elif message.startswith("resolution "):
            s_step = message.split(maxsplit=1)[-1]
            self.steps = int(s_step, 10)
            # self.current_step = 0
            self.send_ok(str(self.steps))

        elif message == "scan":
            self.scan()

        elif message == "quit":
            self.send_text("bye")
            self.close()
        elif message == "scan_check":
            self.scan_check()
        elif message == "calibrate":
            self.calibrate()

        else:
            self.send_error("UNKNOW_COMMAND", message)

    def scan(self):
        if self.mode == 'merge':

            PCD_LOCATION = os.path.join(os.path.dirname(__file__), "..",
                                        "assets")

            if self.current_step < self.steps:
                pc_L = read_pcd(PCD_LOCATION + '/pikachu.pcd')
                tmp = len(pc_L) // self.steps

                self.send_text('{"status": "chunk", "left": %d, "right": 0}' % tmp)
                buf = []
                for p in pc_L[tmp * self.current_step: tmp * (self.current_step + 1)]:
                    buf.append(struct.pack('<' + 'f' * 6, p[0], p[1], p[2],
                               p[3] / 255., p[4] / 255., p[5] / 255.))
                buf = b''.join(buf)
                self.send_binary(buf)

            elif self.current_step < self.steps * 2:
                pc_R = read_pcd(PCD_LOCATION + '/pikachu90.pcd')
                tmp = len(pc_R) // self.steps
                self.send_text('{"status": "chunk", "left": 0, "right": %d}' % tmp)
                buf = []
                for p in pc_R[tmp * (self.current_step - self.steps): tmp * (self.current_step + 1 - self.steps)]:
                    buf.append(struct.pack('<' + 'f' * 6, p[0], p[1], p[2],
                               p[3] / 255., p[4] / 255., p[5] / 255.))
                buf = b''.join(buf)
                self.send_binary(buf)

            else:
                self.send_text('{"status": "chunk", "left": 0, "right": 0}')
                self.send_binary(b'')

            self.current_step += 1
            self.send_ok()

        elif self.mode == 'pcd':
            if self.current_step > 0 or self.current_step > self.steps:
                self.send_text('{"status": "chunk", "left": 0, "right": 0}')
                self.send_binary(b'')
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

        elif self.mode == 'box':
            buf = []
            if self.current_step < self.steps:
                for z in range(500 * self.current_step // self.steps, 500 * (self.current_step + 1) // self.steps, 8):
                    for s in range(-250, 250, 8):
                        buf.append([s, -250, z])
                        buf.append([s, 250, z])
                        buf.append([-250, s, z])
                        buf.append([250, s, z])
                buf = [struct.pack("<ffffff", x / 10, y / 10, z / 10, z / 500., z / 500., (500 - z) / 500) for x, y, z in buf]
            elif self.current_step < self.steps * 2:
                for z in range(500 * (self.current_step - self.steps) // self.steps - 250, 500 * (self.current_step - self.steps + 1) // self.steps - 250, 8):
                    for s in range(-250, 250, 8):
                        buf.append([z, s, 0])
                        buf.append([z, s, 500])
                    for s in range(0, 500, 8):
                        buf.append([z, -250, s])
                        buf.append([z, 250, s])
                buf = [struct.pack("<ffffff", x / 10, y / 10, z / 10, z / 500., z / 500., (500 - z) / 500) for x, y, z in buf]
            else:
                buf = []

            self.send_text('{"status": "chunk", "left": %d, "right": 0}' % len(buf))
            buf = b''.join(buf)
            self.send_binary(buf)
            self.send_ok()

            self.current_step += 1

        elif self.mode == 'cube':
            import random
            buf = []
            if self.current_step < self.steps:
                for x in range(10000 // self.steps):
                    buf.append([random.randint(-250, 250), random.randint(-250, 250), random.randint(500 * self.current_step // self.steps, 500 * (self.current_step + 1) // self.steps)])
                buf = [struct.pack("<ffffff", x / 10, y / 10, z / 10, z / 500., z / 500., (500 - z) / 500) for x, y, z in buf]
            else:
                buf = []

            self.send_text('{"status": "chunk", "left": %d, "right": 0}' % len(buf))
            buf = b''.join(buf)
            self.send_binary(buf)
            self.send_ok()

            self.current_step += 1

    def scan_check(self):
        import random
        s = random.choice(["not open", "not open", "no object", "no object", "good", "didn't pull out laser"])
        self.send_text('{"status": "ok", "message": "%s"}' % (s))

    def calibrate(self):
        self.send_text('{"status": "continue", "message": "please wait until this process done"}')
        from time import sleep
        sleep(10)
        self.send_text('{"status": "ok", "message": "calibration done"}')
