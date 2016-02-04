
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
import random
import struct
import math
import os

from fluxclient.scanner.tools import read_pcd
from fluxclient.scanner import image_to_pc
from fluxclient.scanner.scan_settings import ScanSetting
from fluxclient.hw_profile import HW_PROFILE

from .base import WebSocketBase
from .control import WebsocketControlBase

SIMULATE_IMG_FILE = os.path.join(os.path.dirname(__file__),
                                 "..", "assets", "miku_q.png")
SIMULATE_IMG_MIME = "image/png"
L = logging.getLogger("WS.3DSCAN-CTRL")


class Websocket3DScanControl(WebsocketControlBase):
    ready = False
    steps = 200
    current_step = 0
    proc = None

    def __init__(self, *args, **kw):
        WebsocketControlBase.__init__(self, *args, **kw)
        self.try_control()
        self.scan_settings = ScanSetting()
        self.cab = None

    def on_closed(self):
        self.robot.quit_task()
        self.robot.close()

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

        elif message == "calibrate":
            self.calibrate()
            self.get_cab()

        elif message.startswith('set_params'):
            self.set_params(message)

        elif message.startswith("resolution "):

            s_step = message.split(maxsplit=1)[-1]
            self.steps = int(s_step, 10)
            if self.steps in HW_PROFILE['model-1']['step_setting']:
                self.robot.set_scanlen(HW_PROFILE['model-1']['step_setting'][self.steps][1])
            else:
                self.steps = 400  # this will cause frontend couldn't adjust the numbers of steps
                self.robot.set_scanlen(HW_PROFILE['model-1']['step_setting'][400][1])

            self.scan_settings.scan_step = self.steps
            self.current_step = 0
            self.proc = image_to_pc.image_to_pc(self.steps, self.scan_settings)
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
            self.robot.begin_scan()

        except RuntimeError as err:
            if err.args[0] == "RESOURCE_BUSY":
                self.robot.kick()
            else:
                self.send_error("DEVICE_ERROR", err.args[0])
                return

            ret = self.robot.begin_scan()
            self.send_text('{"status": "ready"}')
            self.ready = True

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
        # s = random.choice(["not open", "not open", "no object", "no object", "good", "no laser"])
        message = self.robot.scan_check()
        message = int(message.split()[-1])
        if message & 1 == 0:
            message = "not open"
        else:
            if message & 2:
                message = "good"
            else:
                message = "no object"
        self.send_text('{"status": "ok", "message": "%s"}' % (message))

    def get_cab(self):
        # self.cab = [float(i) for i in self.robot.get_calibrate().split()[2:]]
        self.cab = True
        tmp = list(map(float, self.robot.get_calibrate().split()[1:]))

        if len(tmp) == 3:
            self.scan_settings.cab_m, self.scan_settings.cab_l, self.scan_settings.cab_r = tmp
        elif len(tmp) == 2:
            self.scan_settings.cab_l += tmp[0]
            self.scan_settings.cab_r += tmp[1]
        else:
            pass
        # self.cameraX += self.scan_settings.cab_m - (self.scan_settings.img_width / 2) / 125 *

        self.scan_settings.LLaserAdjustment = int(self.scan_settings.cab_m) - (self.scan_settings.img_width / 2)
        self.scan_settings.RLaserAdjustment = int(self.scan_settings.cab_m) - (self.scan_settings.img_width / 2)
        # self.scan_settings.LLaserAdjustment /= 2
        # self.scan_settings.RLaserAdjustment /= 2

        self.proc = image_to_pc.image_to_pc(self.steps, self.scan_settings)
        return

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
        left_r, right_r = self.proc.feed(io[1], il[1], ir[1], self.current_step, -self.scan_settings.LLaserAdjustment, -self.scan_settings.RLaserAdjustment)

        self.current_step += 1

        self.send_text('{"status": "chunk", "left": %d, "right": %d}' %
                       (len(left_r), len(right_r)))
        self.send_binary(b''.join(left_r + right_r))
        self.robot.scan_next()
        self.send_ok()

    def calibrate(self):
        self.send_continue()
        res = self.robot.calibrate()
        res = res.split()
        if res[1] == 'fail':
            if res[2] == 'laser':
                m = 'no laser'
            else:
                m = 'no object'
            self.send_text('{"status": "fail", "message": "%s"}' % (m))
        else:
            self.send_text('{"status": "ok"}')

    def set_params(self, message):
        m = message.split()
        if len(m) != 3:
            self.send_error('{} format error'.format(m[1:]))
        key, value = m[1], float(m[2])
        if key in ['MAXLaserRange', 'MINLaserRange', 'LaserRangeMergeDistance', 'LLaserAdjustment', 'RLaserAdjustment', 'MagnitudeThreshold']:
            setattr(self.scan_settings, key, value)
            self.proc = image_to_pc.image_to_pc(self.steps, self.scan_settings)
            self.send_ok()
        else:
            self.send_error('{} key not exist'.format(key))


class SimulateWebsocket3DScanControl(WebSocketBase):
    steps = 200
    current_step = 0
    mode = 'box'
    mode = 'merge'
    model_l = []
    if mode == 'merge':
        PCD_LOCATION = os.path.join(os.path.dirname(__file__), "..", "assets")
        for i in range(1, 10):
            try:
                model_l.append(read_pcd('/var/pcd/%d.pcd' % i))
            except:

                pass
                # raise
    else:
        pass
    if len(model_l) == 0:
        mode = 'box'
    mode = 'box'

    def __init__(self, *args, **kw):
        WebSocketBase.__init__(self, *args)
        with open(SIMULATE_IMG_FILE, "rb") as f:
            self.image_buf = f.read()

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

        elif message == "ping":
            self.send_text('{"status": "pong"}')
            return

        elif message == "quit":
            self.send_text("bye")
            self.close()

        elif message == "scan_check":
            self.scan_check()

        elif message == "calibrate":
            self.calibrate()

        elif message.startswith('set_params'):
            self.set_params(message)

        else:
            self.send_error("UNKNOW_COMMAND", message)

    def scan(self):
        if self.mode == 'merge':

            # PCD_LOCATION = os.path.join(os.path.dirname(__file__), "..", "assets")
            if self.current_step // self.steps < len(self.model_l):
                pc = self.model_l[self.current_step // self.steps]
                tmp = len(pc) // self.steps

                self.send_text('{"status": "chunk", "left": %d, "right": 0}' % tmp)
                buf = []
                for p in pc[tmp * (self.current_step - (self.current_step // self.steps) * self.steps): tmp * ((self.current_step - (self.current_step // self.steps) * self.steps) + 1)]:
                    buf.append(struct.pack('<' + 'f' * 6, p[0], p[1], p[2],
                               p[3] / 255., p[4] / 255., p[5] / 255.))
                buf = b''.join(buf)
                self.send_binary(buf)
            else:
                self.send_text('{"status": "chunk", "left": 0, "right": 0}')
                self.send_binary(b'')

            # if self.current_step < self.steps:

            #     tmp = len(self.pc_L) // self.steps

            #     self.send_text('{"status": "chunk", "left": %d, "right": 0}' % tmp)
            #     buf = []
            #     for p in self.pc_L[tmp * self.current_step: tmp * (self.current_step + 1)]:
            #         buf.append(struct.pack('<' + 'f' * 6, p[0], p[1], p[2],
            #                    p[3] / 255., p[4] / 255., p[5] / 255.))
            #     buf = b''.join(buf)
            #     self.send_binary(buf)

            # elif self.current_step < self.steps * 2:

            #     tmp = len(self.pc_R) // self.steps
            #     self.send_text('{"status": "chunk", "left": %d, "right": 0}' % tmp)
            #     buf = []
            #     for p in self.pc_R[tmp * (self.current_step - self.steps): tmp * (self.current_step + 1 - self.steps)]:
            #         buf.append(struct.pack('<' + 'f' * 6, p[0], p[1], p[2],
            #                    p[3] / 255., p[4] / 255., p[5] / 255.))
            #     buf = b''.join(buf)
            #     self.send_binary(buf)
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
                    for s in range(-125, 125, 8):
                        buf.append([s, -62, z])
                        buf.append([s, 62, z])

                    for s in range(-62, 62, 8):
                        buf.append([-125, s, z])
                        buf.append([125, s, z])
                buf = [struct.pack("<ffffff", x / 10, y / 10, z / 10, z / 500., z / 500., (500 - z) / 500) for x, y, z in buf]

            elif self.current_step < self.steps * 2:
                for z in range(500 * (self.current_step - self.steps) // self.steps - 250, 500 * (self.current_step - self.steps + 1) // self.steps - 250, 8):
                    for s in range(-125, 125, 8):
                        buf.append([z, s, 0])
                        buf.append([z, s, 125])
                    for s in range(0, 125, 8):
                        buf.append([z, -125, s])
                        buf.append([z, 125, s])
                buf = [struct.pack("<ffffff", x / 10, y / 10, z / 10, z / 500., z / 500., (500 - z) / 500) for x, y, z in buf]
            else:
                for z in range(1000):
                    buf.append([random.randint(-99, 99), random.randint(-99, 99), random.randint(0, 990)])
                buf = [struct.pack("<ffffff", x / 10, y / 10, z / 10, 0, 0, 0) for x, y, z in buf]

            # self.send_text('{"status": "chunk", "left": %d, "right": 0}' % len(buf))
            self.send_text('{"status": "chunk", "left": %d, "right": %d}' % (len(buf) // 2, len(buf) // 2))
            buf = b''.join(buf)
            self.send_binary(buf)
            self.send_ok()

            self.current_step += 1

        elif self.mode == 'cube':

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
        s = random.choice(["not open", "not open", "no object", "no object", "good", "no laser"])
        s = "good"
        self.send_text('{"status": "ok", "message": "%s"}' % (s))

    def calibrate(self):
        self.send_continue()
        from time import sleep
        sleep(1)
        self.send_ok()

    def set_params(self, message):
        m = message.split()
        if len(m) != 3:
            self.send_error('{} format error'.format(m[1:]))
        key, value = m[1], float(m[2])
        if key in ['LongestLaserRange', 'LaserRangeMergeDistance', 'LLaserAdjustment', 'RLaserAdjustment']:
            self.config[key] = value
            self.send_ok()
        else:
            self.send_error('{} key not exist'.format(key))
