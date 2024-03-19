import io
import json
import logging

import cv2
import numpy as np
from PIL import Image

from fluxclient.robot.camera import FluxCamera
from fluxclient.utils.version import StrictVersion
from fluxghost.utils.fisheye.calibration import get_remap_img
from fluxghost.utils.fisheye.constants import CHESSBORAD, PERSPECTIVE_SPLIT
from fluxghost.utils.fisheye.corner_detection import apply_points
from fluxghost.utils.fisheye.corner_detection.constants import get_grid
from fluxghost.utils.fisheye.corner_detection.estimate_point import estimate_point
from fluxghost.utils.fisheye.general import pad_image
from fluxghost.utils.fisheye.perspective import apply_perspective_points_transform
from fluxghost.utils.fisheye.rotation import apply_matrix_to_perspective_points, calculate_3d_rotation_matrix

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
fisheye_models = ['fad1', 'ado1']


def camera_api_mixin(cls):
    class CameraAPI(control_base_mixin(cls)):
        def get_robot_from_device(self, device):
            self.remote_version = device.version
            self.remote_model = getattr(device, 'model_id', '')
            self.fisheye_param = None
            self.crop_param = None
            self.camera_3d_rotation = None
            self.rotated_perspective_points = None
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
                elif cmd == 'set_fisheye_matrix':
                    data = msgs[1]
                    self.set_fisheye_matrix(data)
                elif cmd == 'set_crop_param':
                    data = msgs[1]
                    self.set_crop_param(data)
                elif cmd == 'set_3d_rotation':
                    data = msgs[1]
                    self.set_3d_rotation(data)
                elif cmd == 'set_fisheye_height':
                    height = float(msgs[1])
                    self.set_fisheye_height(height)

        def set_fisheye_matrix(self, data):
            data = json.loads(data)
            version = data.get('v', 1)
            if version == 2:
                rvec = np.array(data['rvec'])
                rotation_matrix = cv2.Rodrigues(rvec)[0]
                x_grid, y_grid = get_grid(version)
                self.fisheye_param = {
                    'v': version,
                    'k': np.array(data['k']),
                    'd': np.array(data['d']),
                    'ref_height': data['refHeight'],
                    'points': np.array(data['points']),
                    'xc': np.array(data['xc']),
                    'yc': np.array(data['yc']),
                    'hx': np.array(data['hx']),
                    'hy': np.array(data['hy']),
                    'image_scale': data['imageScale'],
                    'rotation_matrix': rotation_matrix,
                    'x_grid': x_grid,
                    'y_grid': y_grid,
                }
            else:
                perspective_points = data['points']
                self.fisheye_param = {
                    'k': np.array(data['k']),
                    'd': np.array(data['d']),
                    'perspective_points': np.array(perspective_points),
                }
                if self.camera_3d_rotation:
                    self.apply_3d_rotaion_to_perspective_points()
            self.send_ok()

        def set_fisheye_height(self, h):
            if not self.fisheye_param or self.fisheye_param.get('v', 1) != 2:
                raise Exception('Version Mismatch')
            points = self.fisheye_param['points']
            dh = h - self.fisheye_param['ref_height']
            perspective_points = points.copy()
            w, h, _ = perspective_points.shape
            rotation_matrix = self.fisheye_param['rotation_matrix']
            y_grid = self.fisheye_param['y_grid']
            xc = self.fisheye_param['xc']
            yc = self.fisheye_param['yc']
            hx = self.fisheye_param['hx']
            hy = self.fisheye_param['hy']
            s_x, s_y = self.fisheye_param['image_scale']
            for i in range(w):
                for j in range(h):
                    y = y_grid[i]
                    Y = [1, y, y ** 2]
                    x_center, y_center = np.dot(Y, xc), np.dot(Y, yc)
                    h_x, h_y = np.dot(Y, hx), np.dot(Y, hy)
                    p = perspective_points[i][j]
                    p = estimate_point(p, dh, rotation_matrix, x_center, y_center, h_x, h_y, s_x, s_y)
                    perspective_points[i][j] = p
            self.fisheye_param['perspective_points'] = perspective_points
            self.send_ok()

        def set_crop_param(self, data):
            data = json.loads(data)
            self.crop_param = {
                'width': data['width'],
                'height': data['height'],
                'cx': data['cx'],
                'cy': data['cy'],
                'top': data.get('top', None),
                'left': data.get('left', None),
            }
            self.send_ok()

        def set_3d_rotation(self, data):
            data = json.loads(data)
            self.camera_3d_rotation = data
            if self.fisheye_param:
                self.apply_3d_rotaion_to_perspective_points()
            self.send_ok()

        def apply_3d_rotaion_to_perspective_points(self):
            if self.camera_3d_rotation is None or self.fisheye_param is None:
                return
            rx = self.camera_3d_rotation['rx']
            ry = self.camera_3d_rotation['ry']
            rz = self.camera_3d_rotation['rz']
            h = self.camera_3d_rotation['h']
            self.rotated_perspective_points = apply_matrix_to_perspective_points(
                self.fisheye_param['perspective_points'], calculate_3d_rotation_matrix(rx, ry, rz), h
            )

        def handle_fisheye_image(self, open_cv_img, downsample=1):
            version = self.fisheye_param.get('v', 1)
            if version == 1:
                perspective_points = (
                    self.rotated_perspective_points
                    if self.rotated_perspective_points is not None
                    else self.fisheye_param['perspective_points']
                )
                img = apply_perspective_points_transform(
                    open_cv_img,
                    self.fisheye_param['k'],
                    self.fisheye_param['d'],
                    PERSPECTIVE_SPLIT,
                    CHESSBORAD,
                    perspective_points,
                    downsample=downsample
                )
                if self.crop_param is not None:
                    cx = self.crop_param['cx']
                    cy = self.crop_param['cy']
                    if self.camera_3d_rotation is not None:
                        cx += self.camera_3d_rotation['tx']
                        cy += self.camera_3d_rotation['ty']
                    img = crop_transformed_img(
                        img,
                        cx,
                        cy,
                        width=self.crop_param['width'],
                        height=self.crop_param['height'],
                        top=self.crop_param['top'],
                        left=self.crop_param['left'],
                    )
            elif version == 2:
                k = self.fisheye_param['k']
                d = self.fisheye_param['d']
                x_grid = self.fisheye_param['x_grid']
                y_grid = self.fisheye_param['y_grid']
                img = pad_image(open_cv_img)
                if downsample > 1:
                    img = cv2.resize(img, (img.shape[1] // downsample, img.shape[0] // downsample))
                    k = k.copy()
                    k[0][0] /= downsample
                    k[1][1] /= downsample
                    k[0][2] /= downsample
                    k[1][2] /= downsample
                    img = get_remap_img(img, k, d)
                    img = cv2.resize(img, (img.shape[1] * downsample, img.shape[0] * downsample))
                else:
                    img = get_remap_img(img, k, d)
                padding = 150
                img = apply_points(img, self.fisheye_param['perspective_points'], x_grid, y_grid, padding=padding)
                img = img[padding:, padding:]
            return img

        def on_image(self, camera, image):
            logger.debug('on_image')
            if self.remote_model in fisheye_models and self.fisheye_param is not None:
                try:
                    img = Image.open(io.BytesIO(image))
                    open_cv_img = np.array(img)
                    open_cv_img = cv2.cvtColor(open_cv_img, cv2.COLOR_RGBA2BGR)
                except Exception:
                    self.send_binary(image)
                    return
                img = self.handle_fisheye_image(open_cv_img, downsample=1)
                _, array_buffer = cv2.imencode('.jpg', img)
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
