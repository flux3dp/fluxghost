import io
import json
import logging

import cv2
import numpy as np
from PIL import Image

from fluxclient.robot.camera import FluxCamera
from fluxclient.utils.version import StrictVersion
from fluxghost.utils.fisheye.general import CHESSBORAD, PERSPECTIVE_SPLIT
from fluxghost.utils.fisheye.perspective import apply_perspective_points_transform

from .camera_calibration import crop_transformed_img
from .control_base import control_base_mixin

CRITICAL_VERSION = StrictVersion('1.0')
logger = logging.getLogger('API.CAMERA')


'''
Control printer

Javascript Example:

ws = new WebSocket('ws://127.0.0.1:8000/ws/control/RLFPAPI7E8KXG64KG5NOWWY3T');
ws.onmessage = function(v) { console.log(v.data);}
ws.onclose = function(v) { console.log('CONNECTION CLOSED, code=' + v.code +
    '; reason=' + v.reason); }

// After recive connected...
ws.send('ls')
'''

def camera_api_mixin(cls):
    class CameraAPI(control_base_mixin(cls)):
        def get_robot_from_device(self, device):
            self.remote_version = device.version
            self.remote_model = getattr(device, 'model_id', '')
            self.fisheye_param = None
            self.crop_param = None
            return device.connect_camera(
                self.client_key, conn_callback=self._conn_callback)

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
                elif cmd == 'set_fisheye_matrix':
                    data = msgs[1]
                    self.set_fisheye_matrix(data)
                elif cmd == 'set_crop_param':
                    data = msgs[1]
                    self.set_crop_param(data)


        def set_fisheye_matrix(self, data):
            data = json.loads(data)
            self.fisheye_param = {
                'k': np.array(data['k']),
                'd': np.array(data['d']),
                'corners': np.array(data['corners']),
            }
            self.send_ok()

        def set_crop_param(self, data):
            data = json.loads(data)
            self.crop_param = {
                'width': data['width'],
                'height': data['height'],
                'cx': data['cx'],
                'cy': data['cy'],
            }
            self.send_ok()

        def on_image(self, camera, image):
            if self.remote_model == 'fad1' and self.fisheye_param is not None:
                try:
                    img = Image.open(io.BytesIO(image))
                    open_cv_img = np.array(img)
                    open_cv_img = cv2.cvtColor(open_cv_img, cv2.COLOR_RGBA2BGR)
                except Exception:
                    self.send_binary(image)
                    return
                img = apply_perspective_points_transform(
                    open_cv_img,
                    self.fisheye_param['k'],
                    self.fisheye_param['d'],
                    PERSPECTIVE_SPLIT,
                    CHESSBORAD,
                    self.fisheye_param['corners']
                )
                if self.crop_param is not None:
                    img = crop_transformed_img(img, self.crop_param['cx'], self.crop_param['cy'], self.crop_param['width'], self.crop_param['height'])
                _, array_buffer = cv2.imencode('.png', img)
                img_bytes = array_buffer.tobytes()
                self.send_binary(img_bytes)
            else:
                self.send_binary(image)
    return CameraAPI


class CameraWrapper(object):
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
