
import logging
from math import pi, cos, sin
import struct

from fluxclient.scanner.scan_settings import ScanSetting
from fluxclient.robot.errors import RobotError
from fluxclient.hw_profile import HW_PROFILE
from fluxclient.scanner import image_to_pc
from fluxclient.robot import errors

# from .control_base import control_base_mixin

logger = logging.getLogger("API.SCAN_CONTROL_SIM")


from io import BytesIO
from uuid import UUID
import logging
import socket
import pkg_resources
import random

from fluxclient.encryptor import KeyObject
from fluxclient.robot.errors import RobotError, RobotSessionError

STAGE_DISCOVER = '{"status": "connecting", "stage": "discover"}'
STAGE_ROBOT_CONNECTING = '{"status": "connecting", "stage": "connecting"}'
STAGE_CONNECTED = '{"status": "connected"}'
STAGE_TIMEOUT = '{"status": "error", "error": "TIMEOUT"}'


def control_base_mixin(cls):
    class ControlBaseAPI(cls):
        binary_handler = None
        cmd_mapping = None
        client_key = None
        robot = None

        def __init__(self, *args, **kw):
            super().__init__(*args)
            # self.uuid = UUID(hex=kw["serial"])
            self.POOL_TIME = 1.5

        def on_connected(self):
            pass

        def on_loop(self):
            if self.client_key and not self.robot:
                self.try_connect()

        def get_robot_from_device(self, device):
            return device.connect_robot(
                self.client_key, conn_callback=self._conn_callback)

        def try_connect(self):
            self.robot = True
            self.send_text(STAGE_DISCOVER)
            logger.debug("DISCOVER")

            # if uuid in self.server.discover_devices:
            #     device = self.server.discover_devices[uuid]
            #     self.remote_version = device.version
            #     self.ipaddr = device.ipaddr
            #     self.send_text(STAGE_ROBOT_CONNECTING)
            self.send_text(STAGE_ROBOT_CONNECTING)
            #     try:
            #         self.robot = self.get_robot_from_device(device)

            #     except (OSError, ConnectionError, socket.timeout) as e:  # noqa
            #         logger.error("Socket erorr: %s", e)
            #         self.send_fatal("DISCONNECTED")

            #     except (RobotError, RobotSessionError) as err:
            #         if err.error_symbol[0] == "REMOTE_IDENTIFY_ERROR":
            #             self.server.discover_devices.pop(uuid)
            #             self.server.discover.devices.pop(uuid)
            #         self.send_fatal(*err.error_symbol)
            #         return

            #     self.send_text(STAGE_CONNECTED)
            #     self.POOL_TIME = 30.0
            #     self.on_connected()
            self.send_text(STAGE_CONNECTED)
            self.POOL_TIME = 30.0
            self.on_connected()

        def on_text_message(self, message):
            if self.client_key:
                self.on_command(message)
            else:
                # self.client_key = True
                try:
                    self.client_key = KeyObject.load_keyobj(message)
                except ValueError:
                    self.send_fatal("BAD_PARAMS")
                except Exception:
                    logger.error("RSA Key load error: %s", message)
                    self.send_fatal("BAD_PARAMS")
                    raise
                self.try_connect()

        def on_binary_message(self, buf):
            try:
                if self.binary_handler:
                    self.binary_handler(buf)
                else:
                    self.send_fatal("PROTOCOL_ERROR",
                                    "Can not accept binary data")
            except RobotSessionError as e:
                logger.debug("RobotSessionError%s [error_symbol=%s]",
                             repr(e.args), e.error_symbol)
                self.send_fatal(*e.error_symbol)

        def cb_upload_callback(self, robot, sent, size):
            self.send_json(status="uploading", sent=sent)

        def simple_binary_transfer(self, method, mimetype, size,
                                   upload_to=None, cb=None):
            ref = method(mimetype, size, upload_to)

            def binary_handler(buf):
                try:
                    feeder = ref.__next__()
                    sent = feeder(buf)
                    self.send_json(status="uploading", sent=sent)
                    if sent == size:
                        ref.__next__()
                except StopIteration:
                    self.binary_handler = None
                    cb()

            ref.__next__()
            self.binary_handler = binary_handler
            self.send_continue()

        def simple_binary_receiver(self, size, continue_cb):
            swap = BytesIO()
            upload_meta = {'sent': 0}

            def binary_handler(buf):
                swap.write(buf)
                sent = upload_meta['sent'] = upload_meta['sent'] + len(buf)

                if sent < size:
                    pass
                elif sent == size:
                    self.binary_handler = None
                    continue_cb(swap)
                else:
                    self.send_fatal("NOT_MATCH", "binary data length error")

            self.binary_handler = binary_handler
            self.send_continue()

        def _fix_auth_error(self, task):
            self.send_text(STAGE_DISCOVER)
            if task.timedelta < -15:
                logger.warn("Auth error, try fix time delta")
                old_td = task.timedelta
                task.reload_remote_profile(lookup_timeout=30.)
                if task.timedelta - old_td > 0.5:
                    # Fix timedelta issue let's retry
                    p = self.server.discover_devices.get(self.uuid)
                    if p:
                        p["timedelta"] = task.timedelta
                        self.server.discover_devices[self.uuid] = p
                        return True
            return False

        def on_closed(self):
            if self.robot:
                self.robot.close()
                self.robot = None
            self.cmd_mapping = None

        def _disc_callback(self, *args):
            self.send_text(STAGE_DISCOVER)
            return True

        def _conn_callback(self, *args):
            self.send_text(STAGE_ROBOT_CONNECTING)
            return True
    return ControlBaseAPI


def scan_control_api_mixin_sim(cls):
    class ScanControlApi(control_base_mixin(cls)):
        task = None
        steps = 200
        current_step = 0
        proc = None

        def __init__(self, *args, **kw):
            super().__init__(*args, **kw)
            self.scan_settings = ScanSetting()
            self.cab = True

        def on_closed(self):
            if self.robot:
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
                self.scan_check()

            elif message == "calibrate":
                self.calibrate()
                self.get_cab()

            elif message.startswith('set_params'):
                self.set_params(message)

            elif message.startswith("resolution "):

                s_step = message.split(maxsplit=1)[-1]
                self.steps = int(s_step, 10)
                # if self.steps in HW_PROFILE['model-1']['step_setting']:
                #     self.task.step_length(
                #         HW_PROFILE['model-1']['step_setting'][self.steps][1])
                # else:
                #     # this will cause frontend couldn't adjust the numbers of
                #     # steps
                #     self.steps = 400
                #     self.task.step_length(
                #         HW_PROFILE['model-1']['step_setting'][400][1])

                self.scan_settings.scan_step = self.steps
                self.current_step = 0
                self.proc = image_to_pc.image_to_pc(self.steps,
                                                    self.scan_settings)
                self.send_ok(info=str(self.steps))

            elif message.startswith("scan"):
                if self.cab is None:
                    self.get_cab()
                if len(message.split()) > 1:
                    self.scan(step=int(message.split()[1]))
                else:
                    self.scan()

            elif message == "quit":
                self.task.quit()
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
            if self.task:
                self.send_error("ALREADY_READY")
                return

            try:
                # self.task = self.robot.scan()
                self.send_text('{"status": "ready"}')

            except RobotError as err:
                if err.error_symbol[0] == "RESOURCE_BUSY":
                    self.send_error('DEVICE_BUSY', err.args[-1])
                else:
                    self.send_error(err.error_symbol[0], *err.error_symbol[1:])

        def take_control(self):
            if self.task:
                self.send_error("ALREADY_READY")
                return

            try:
                self.robot.scan()

            except RobotError as err:
                if err.args[0] == "RESOURCE_BUSY":
                    self.robot.kick()
                else:
                    self.send_error("DEVICE_ERROR", err.args[0])
                    return

                self.task = self.robot.scan()
                self.send_text('{"status": "ready"}')

        def fetch_image(self):
            file_name = random.choice(["assets/grid.png", "assets/flux3dp-icon.png"])

            images = [('image/jpeg', open(pkg_resources.resource_filename("fluxclient", file_name), 'rb').read())]

            for mime, buf in images:
                self.send_binary_begin(mime, len(buf))
                self.send_binary(buf)
            self.send_ok()

        def scan_check(self):
            # message = self.task.check_camera()
            # message = int(message.split()[-1])
            # if message & 1 == 0:
            #     message = "not open"
            # else:
            #     if message & 2:
            #         message = "good"
            #     else:
            #         message = "no object"
            message = "good"
            self.send_text('{"status": "ok", "message": "%s"}' % (message))

        def get_cab(self):
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
            logger.info('callibration: m:{} l:{} r:{}'.format(
                self.scan_settings.cab_m, self.scan_settings.cab_l,
                self.scan_settings.cab_r))

            l = int(self.scan_settings.cab_m) - \
                (self.scan_settings.img_width / 2)
            r = int(self.scan_settings.cab_m) - \
                (self.scan_settings.img_width / 2)
            self.scan_settings.LLaserAdjustment = l
            self.scan_settings.RLaserAdjustment = r

            self.proc = image_to_pc.image_to_pc(self.steps, self.scan_settings)
            return

        def scan(self, step=None):
            if step:
                self.current_step = step

            logger.debug('Do scan %d/%d' % (self.current_step, self.steps))

            phi = self.current_step * 2 * pi / self.steps
            sample_n = 100
            r_l = 40
            r_r = 50

            # x = sin(theta) * cos(phi) * r
            # y = sin(theta) * sin(phi) * r
            # z = r * cos(theta)
            point_L = []
            point_R = []
            for t in range(sample_n):
                theta = t * 2 * pi / sample_n
                x = sin(theta) * cos(phi)
                y = sin(theta) * sin(phi)
                z = cos(theta)
                point_L.append([x * r_l, y * r_l, z * r_l + r_l / 2, 0, 0, 0])
                point_R.append([x * r_r, y * r_r, z * r_r + r_r / 2, 255, 0, 0])

            # point_L
            # point_R
            points_to_bytes = lambda points: [struct.pack('<ffffff', p[0], p[1], p[2], p[3] / 255., p[4] / 255., p[5] / 255.) for p in points]
            left_r = points_to_bytes(point_L)
            right_r = points_to_bytes(point_R)

            self.send_text('{"status": "chunk", "left": %d, "right": %d}' %
                           (len(left_r), len(right_r)))
            self.send_binary(b''.join(left_r + right_r))
            # self.task.forward()
            # from time import sleep
            # sleep(1)
            self.send_ok()
            self.current_step += 1

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
                self.proc = image_to_pc.image_to_pc(self.steps,
                                                    self.scan_settings)
                self.send_ok()
            else:
                self.send_error('{} key not exist'.format(key))
    return ScanControlApi
