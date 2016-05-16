
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

from fluxclient.robot import errors
from fluxclient.scanner.tools import read_pcd
from fluxclient.scanner import image_to_pc
from fluxclient.scanner.scan_settings import ScanSetting
from fluxclient.hw_profile import HW_PROFILE

from .base import WebSocketBase
from .control import WebsocketControlBase
from fluxclient.robot.errors import RobotError

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
        self.scan_settings = ScanSetting()
        self.cab = None

    def on_closed(self):
        if self.robot:
            self.robot.quit_task()
            self.robot.close()

    def on_binary_message(self, buf):
        self.text_send("Protocol error")
        self.close()

    def on_connected(self):
        self.try_control()

    def on_command(self, message):
        if message == "take_control":
            self.take_control()

        elif message == "retry":
            self.try_control()

        elif message == "image":
            self.fetch_image()

        elif message == "scan_check":
            try:
                self.scan_check()
            except errors.RobotDisconnected():
                self.send_fatal("DISCONNECTED")

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

        elif message.startswith("scan"):
            try:
                if self.cab is None:
                    self.get_cab()
                if len(message.split()) > 1:
                    self.scan(step=int(message.split()[1]))
                else:
                    self.scan()
            except Exception:
                self.send_fatal

        elif message == "quit":
            if self.robot.position() == "ScanTask":
                self.robot.quit_task()
            self.send_text("bye")
            self.close()
#########################
        elif message == 'fatal':
            del self.robot
            self.send_fatal('fatal by command')
#########################
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

        except (RuntimeError, RobotError) as err:
            if err.args[0] == "RESOURCE_BUSY":
                self.send_error('DEVICE_BUSY', err.args[-1])
            else:
                self.send_error('DEVICE_ERROR', err.args[0])

    def take_control(self):
        if self.ready:
            self.send_error("ALREADY_READY")

        try:
            self.robot.begin_scan()

        except (RuntimeError, RobotError) as err:
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
        L.info('callibration: m:{} l:{} r:{}'.format(self.scan_settings.cab_m, self.scan_settings.cab_l, self.scan_settings.cab_r))
        # self.cameraX += self.scan_settings.cab_m - (self.scan_settings.img_width / 2) / 125 *

        self.scan_settings.LLaserAdjustment = int(self.scan_settings.cab_m) - (self.scan_settings.img_width / 2)
        self.scan_settings.RLaserAdjustment = int(self.scan_settings.cab_m) - (self.scan_settings.img_width / 2)
        # self.scan_settings.LLaserAdjustment /= 2
        # self.scan_settings.RLaserAdjustment /= 2

        self.proc = image_to_pc.image_to_pc(self.steps, self.scan_settings)
        return

    def scan(self, step=None):
        if not self.ready:
            self.send_error("NOT_READY")
            return

        if not self.proc:
            self.send_error("BAD_PARAMS", "resolution")
            return

        if step:
            self.current_step = step

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
