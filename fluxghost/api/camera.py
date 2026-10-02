import io
import logging
from time import perf_counter

import cv2
import numpy as np
from PIL import Image

from fluxclient.robot.camera import FluxCamera
from fluxclient.utils.version import StrictVersion

from .control_base import control_base_mixin
from .fisheye_camera_mixin import FisheyeCameraMixin

CRITICAL_VERSION = StrictVersion('1.0')
logger = logging.getLogger('API.CAMERA')


"""
Control printer

Javascript Example:

ws = new WebSocket('ws://127.0.0.1:8000/ws/control/RLFPAPI7E8KXG64KG5NOWWY3T');
ws.onmessage = function(v) { console.log(v.data);}
ws.onclose = function(v) { console.log('CONNECTION CLOSED, code=' + v.code +
    '; reason=' + v.reason); }

// After recive connected...
ws.send('ls')
"""
fisheye_models = ['fad1', 'ado1', 'fbb2', 'fbm2', 'fhx2rf']


def camera_api_mixin(cls):
    class CameraAPI(FisheyeCameraMixin, control_base_mixin(cls)):
        is_next_image_low_resolution = False
        preview_downsample = 1
        frame_requested_at = None
        first_byte_at = None
        read_count = 0

        def get_robot_from_device(self, device):
            self.remote_version = device.version
            self.remote_model = getattr(device, 'model_id', '')
            self.reset_params()
            return device.connect_camera(self.client_key, conn_callback=self._conn_callback)

        def get_robot_from_h2h(self, usbprotocol):
            return FluxCamera.from_usb(self.client_key, usbprotocol)

        def on_connected(self):
            self.rlist.append(CameraWrapper(self, self.robot))

        def on_command(self, message):
            logger.info(message)
            msgs = message.split(' ', 1)
            cmd = msgs[0]
            if self.remote_version > CRITICAL_VERSION:
                if cmd == 'enable_streaming':
                    self.robot.enable_streaming()
                elif cmd == 'require_frame':
                    self.frame_requested_at = perf_counter()
                    self.first_byte_at = None
                    self.read_count = 0
                    logger.info('[timing] frame requested')
                    if len(msgs) > 1 and msgs[1] == 'l':
                        self.robot.require_frame(True)
                        self.is_next_image_low_resolution = True
                        return
                    self.robot.require_frame()
                elif cmd == 'set_3d_rotation':
                    data = msgs[1]
                    self.set_3d_rotation(data)
                elif cmd == 'get_camera_count':
                    success, data = self.robot.send_text('camera_number')
                    self.send_ok(success=success, data=data.decode())
                elif cmd.startswith('set_camera'):
                    idx = int(msgs[1])
                    success, data = self.robot.send_text('camera_change:%d' % idx)
                    self.send_ok(success=success, data=data.decode())
                elif cmd == 'send_text':
                    text = msgs[1]
                    success, data = self.robot.send_text(text)
                    self.send_ok(success=success, data=data.decode())
                else:
                    super().on_command(message)

        def on_image(self, camera, image):
            is_low_resolution = self.is_next_image_low_resolution
            self.is_next_image_low_resolution = False
            t_recv = perf_counter()
            if self.frame_requested_at is not None:
                first_byte = self.first_byte_at or t_recv
                logger.info(
                    '[timing] image received: %d bytes, %.1f ms after request '
                    '(first byte after %.1f ms, then %.1f ms over %d socket reads)',
                    len(image),
                    (t_recv - self.frame_requested_at) * 1000,
                    (first_byte - self.frame_requested_at) * 1000,
                    (t_recv - first_byte) * 1000,
                    self.read_count,
                )
                self.frame_requested_at = None
            else:
                logger.info('[timing] image received: %d bytes (streaming)', len(image))
            if self.remote_model in fisheye_models and self.fisheye_param is not None:
                try:
                    img = Image.open(io.BytesIO(image))
                    cv_img = np.array(img)
                    cv_img = cv2.cvtColor(cv_img, cv2.COLOR_RGBA2BGR)
                except Exception:
                    self.send_binary(image)
                    return
                t_decoded = perf_counter()
                # Low-memory devices OOM inside cv2 at full resolution; retry the frame
                # downsampled and stick with it for the rest of the connection
                while True:
                    try:
                        img = self.handle_fisheye_image(
                            cv_img, downsample=self.preview_downsample, is_low_resolution=is_low_resolution
                        )
                        break
                    except (cv2.error, MemoryError):
                        if self.preview_downsample >= 4:
                            logger.exception('Failed to process fisheye image, dropping frame')
                            return
                        self.preview_downsample *= 2
                        logger.warning(
                            'cv2 error (likely OOM), retrying preview at downsample %d', self.preview_downsample
                        )
                t_fisheye = perf_counter()
                _, array_buffer = cv2.imencode('.jpg', img)
                img_bytes = array_buffer.tobytes()
                self.send_binary(img_bytes)
                t_sent = perf_counter()
                logger.info(
                    '[timing] decode %.1f ms, fisheye %.1f ms, encode+send %.1f ms, total %.1f ms',
                    (t_decoded - t_recv) * 1000,
                    (t_fisheye - t_decoded) * 1000,
                    (t_sent - t_fisheye) * 1000,
                    (t_sent - t_recv) * 1000,
                )
            else:
                self.send_binary(image)

    return CameraAPI


class CameraWrapper:
    def __init__(self, ws, camera):
        self.ws = ws
        self.camera = camera
        # TODO: `camera.sock.fileno()` to `camera.fileno()`
        self._fileno = camera.sock.fileno()

    def fileno(self):
        return self._fileno

    def on_read(self):
        if self.ws.first_byte_at is None:
            self.ws.first_byte_at = perf_counter()
        self.ws.read_count += 1
        try:
            self.camera.feed(self.ws.on_image)
        except RuntimeError as e:
            logger.info('Camera error: %s', e)
            self.ws.close()
            self.camera = None
            self.ws = None
