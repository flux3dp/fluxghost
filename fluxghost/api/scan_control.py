
from PIL import Image
from io import BytesIO
import logging

from fluxclient.scanner.scan_settings import ScanSetting
from fluxclient.robot.errors import RobotError
from fluxclient.hw_profile import HW_PROFILE
from fluxclient.scanner import image_to_pc
from fluxclient.robot import errors

from .control_base import control_base_mixin

logger = logging.getLogger("API.SCAN_CONTROL")


def scan_control_api_mixin(cls):
    class ScanControlApi(control_base_mixin(cls)):
        task = None
        steps = 200
        current_step = 0
        proc = None

        def __init__(self, *args, **kw):
            super().__init__(*args, **kw)
            self.scan_settings = ScanSetting()
            self.cab = None

        def on_closed(self):
            if self.robot:
                self.robot.close()

        def on_binary_message(self, buf):
            self.text_send("Protocol error")
            self.close()

        def _setup_task(self):
            self.task = self.robot.scan()
            mimetype, buf = self.task.oneshot()[0]
            img = Image.open(BytesIO(buf))
            w, h = img.size
            self.scan_settings.set_camera(w, h)
            self.proc = image_to_pc.image_to_pc(self.steps, self.scan_settings)

        def on_connected(self):
            self.try_control()

        def on_command(self, message):
            if message == "take_control":
                self.take_control()

            elif message == "turn_on_hd":
                # No use, just prevent error
                self.send_ok()

            elif message == "retry":
                self.try_control()

            elif message == "image":
                self.fetch_image()

            elif message == "scan_check":
                try:
                    self.scan_check()
                except errors.RobotSessionError:
                    self.send_fatal("DISCONNECTED")

            elif message == "calibrate":
                self.calibrate()
                self.get_cab()

            elif message.startswith("turn_on_laser"):
                self.turn_laser(True)

            elif message.startswith("turn_off_laser"):
                self.turn_laser(False)

            elif message.startswith('set_params'):
                self.set_params(message)

            elif message.startswith("resolution "):
                s_step = message.split(maxsplit=1)[-1]
                self.steps = int(s_step, 10)
                if self.steps in HW_PROFILE['model-1']['step_setting']:
                    self.task.step_length(
                        HW_PROFILE['model-1']['step_setting'][self.steps][1])
                else:
                    # this will cause frontend couldn't adjust the numbers of
                    # steps
                    self.steps = 400
                    self.task.step_length(
                        HW_PROFILE['model-1']['step_setting'][400][1])

                self.scan_settings.scan_step = self.steps
                self.current_step = 0
                self.proc.steps = self.steps
                self.send_ok(info=str(self.steps))

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
                self.task.quit()
                self.send_text("bye")
                self.close()
            else:
                self.send_error("L_UNKNOW_COMMAND")

        def try_control(self):
            if self.task:
                self.send_error("ALREADY_READY")
                return

            try:
                self._setup_task()
                self.send_json(status="ready")

            except RobotError as err:
                if err.error_symbol[0] == "RESOURCE_BUSY":
                    self.send_error('DEVICE_BUSY')
                else:
                    self.send_error(err.error_symbol)

        def take_control(self):
            if self.task:
                self.send_error("ALREADY_READY")
                return

            try:
                self._setup_task()
                self.send_json(status="ready")

            except RobotError as err:
                if err.args[0] == "RESOURCE_BUSY":
                    self.robot.kick()
                    self.try_control()
                else:
                    self.send_error(err.args)
                    return

        def fetch_image(self):
            if not self.task:
                self.send_error("NOT_READY")
                return

            images = self.task.oneshot()
            for mime, buf in images:
                self.send_binary_begin(mime, len(buf))
                self.send_binary(buf)
            self.send_ok()

        def scan_check(self):
            if not self.task:
                self.send_error("NOT_READY")
                return
            message = self.task.check_camera()
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
            if not self.task:
                self.send_error("NOT_READY")
                return
            self.cab = True
            tmp = list(map(float, self.task.get_calibrate().split()[1:]))

            if len(tmp) == 3:
                self.scan_settings.cab_m, self.scan_settings.cab_l, \
                    self.scan_settings.cab_r = tmp
            elif len(tmp) == 2:
                self.scan_settings.cab_l += tmp[0]
                self.scan_settings.cab_r += tmp[1]
            else:
                pass
            logger.info('  callibration: m:{} l:{} r:{}'.format(
                self.scan_settings.cab_m, self.scan_settings.cab_l,
                self.scan_settings.cab_r))

            l = int(self.scan_settings.cab_m) - \
                (self.scan_settings.img_width / 2)
            r = int(self.scan_settings.cab_m) - \
                (self.scan_settings.img_width / 2)
            self.scan_settings.LLaserAdjustment = l
            self.scan_settings.RLaserAdjustment = r

        def turn_laser(self, laser_onoff):
            if not self.task:
                self.send_error("NOT_READY")
                return

            self.task.laser(laser_onoff, laser_onoff)
            self.send_ok()

        def scan(self, step=None):
            if not self.task:
                self.send_error("NOT_READY")
                return

            if not self.proc:
                self.send_error("BAD_PARAMS", info="resolution")
                return

            if step:
                self.current_step = step

            il, ir, io = self.task.scanimages()
            self.task.forward()
            left_r, right_r = self.proc.feed(
                io[1], il[1], ir[1], self.current_step,
                -self.scan_settings.LLaserAdjustment,
                -self.scan_settings.RLaserAdjustment)

            self.current_step += 1

            self.send_text('{"status": "chunk", "left": %d, "right": %d}' %
                           (len(left_r), len(right_r)))
            self.send_binary(b''.join(left_r + right_r))
            self.send_ok()

        def calibrate(self):
            self.send_continue()
            res = self.task.calibrate()
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
            if key in ['MAXLaserRange',
                       'MINLaserRange',
                       'LaserRangeMergeDistance',
                       'LLaserAdjustment',
                       'RLaserAdjustment',
                       'MagnitudeThreshold']:
                setattr(self.scan_settings, key, value)
                self.send_ok()
            else:
                self.send_error('{} key not exist'.format(key))
    return ScanControlApi
