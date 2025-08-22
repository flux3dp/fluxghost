import io
import logging

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
fisheye_models = ['fad1', 'ado1', 'fbb2', 'fbm2']


def camera_api_mixin(cls):
    class CameraAPI(FisheyeCameraMixin, control_base_mixin(cls)):
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
                    self.robot.require_frame()
                elif cmd == 'set_3d_rotation':
                    data = msgs[1]
                    self.set_3d_rotation(data)
                elif cmd == 'get_camera_count':
                    success, data = self.robot.get_camera_counts()
                    self.send_ok(success=success, data=data.decode())
                elif cmd.startswith('set_camera'):
                    idx = int(msgs[1])
                    success, data = self.robot.set_camera(idx)
                    self.send_ok(success=success, data=data.decode())
                elif cmd == 'send_text':
                    text = msgs[1]
                    success, data = self.robot.send_text(text)
                    self.send_ok(success=success, data=data.decode())
                else:
                    super().on_command(message)

        def on_image(self, camera, image):
            logger.debug('on_image')
            if self.remote_model in fisheye_models and self.fisheye_param is not None:
                try:
                    img = Image.open(io.BytesIO(image))
                    cv_img = np.array(img)
                    cv_img = cv2.cvtColor(cv_img, cv2.COLOR_RGBA2BGR)
                except Exception:
                    self.send_binary(image)
                    return
                img = self.handle_fisheye_image(cv_img, downsample=1)
                _, array_buffer = cv2.imencode('.jpg', img)
                img_bytes = array_buffer.tobytes()
                self.send_binary(img_bytes)
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
        try:
            self.camera.feed(self.ws.on_image)
        except RuntimeError as e:
            logger.info('Camera error: %s', e)
            self.ws.close()
            self.camera = None
            self.ws = None
