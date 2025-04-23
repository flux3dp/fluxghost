import json
import logging

import cv2
import numpy as np

from fluxclient.hw_profile import HW_PROFILE
from fluxghost.utils.fisheye.calibration import get_remap_img, remap_corners
from fluxghost.utils.fisheye.constants import CHESSBOARD, PERSPECTIVE_SPLIT
from fluxghost.utils.fisheye.corner_detection import apply_points
from fluxghost.utils.fisheye.general import pad_image
from fluxghost.utils.fisheye.perspective import apply_perspective_points_transform
from fluxghost.utils.fisheye.rotation import apply_matrix_to_perspective_points, calculate_3d_rotation_matrix


logger = logging.getLogger(__file__)

CX = 1321
CY = 1100
DPMM = 5

# deprecated v1 functions
def crop_transformed_img(img, cx=CX, cy=CY, width=430, height=300, top=None, left=None):
    cx = int(cx)
    cy = int(cy)
    width = int(width) * DPMM
    height = int(height) * DPMM
    left = cx - width // 2 if left is None else cx - int(left) * DPMM
    top = cy - height // 2 if top is None else cy - int(top) * DPMM
    img = img[top : top + height, left : left + width]
    return img

def generate_grid_objects(grid_data_x, grid_data_y):
    x_start, x_end, x_step = grid_data_x
    y_start, y_end, y_step = grid_data_y
    xgrid = np.arange(x_start, x_end + 1, x_step)
    if xgrid[-1] != x_end:
        xgrid = np.append(xgrid, x_end)
    ygrid = np.arange(y_start, y_end + 1, y_step)
    if ygrid[-1] != y_end:
        ygrid = np.append(ygrid, y_end)
    xx, yy = np.meshgrid(xgrid, ygrid)
    objp = np.dstack([xx, yy, np.zeros_like(xx)])

    return xgrid, ygrid, objp

class FisheyeCameraMixin:
    cmd_mapping = None
    fisheye_param = None
    leveling_data = None
    perspective_points = None
    # deprecated v1 parameters
    crop_param = None
    camera_3d_rotation = None
    rotated_perspective_points = None

    def __init__(self, *args, **kw):
        super(FisheyeCameraMixin, self).__init__(*args, **kw)
        self.cmd_mapping = {
            'set_fisheye_matrix': [self.set_fisheye_matrix],
            'set_leveling_data': [self.set_leveling_data],
            'set_fisheye_grid': [self.set_fisheye_grid],
        }

    def on_command(self, message):
        msgs = message.split(' ', 1)
        cmd = msgs[0]
        data = msgs[1] if len(msgs) > 1 else ''
        if cmd == 'set_fisheye_matrix':
            self.set_fisheye_matrix(data)
        elif cmd == 'set_leveling_data':
            self.set_leveling_data(data)
        elif cmd == 'set_fisheye_grid':
            self.set_fisheye_grid(data)
        elif cmd == 'set_fisheye_height':
            height = float(msgs[1])
            remote_model = getattr(self, 'remote_model', None)
            self.set_fisheye_height(height, remote_model)
        # deprecated v1 commands
        elif cmd == 'set_crop_param':
            self.set_crop_param(data)
        elif cmd == 'set_3d_rotation':
            self.set_3d_rotation(data)

    def reset_params(self):
        self.fisheye_param = None
        self.leveling_data = None
        self.perspective_points = None
        # deprecated v1 parameters
        self.crop_param = None
        self.camera_3d_rotation = None
        self.rotated_perspective_points = None

    # deprecated v1 functions
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

    # deprecated v1 functions
    def set_3d_rotation(self, data):
        data = json.loads(data)
        self.camera_3d_rotation = data
        if self.fisheye_param:
            self.apply_3d_rotaion_to_perspective_points()
        self.send_ok()

    # deprecated v1 functions
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

    def set_fisheye_matrix(self, data):
        data = json.loads(data)
        version = data.get('v', 1)
        if version == 1:
            logger.warning('Deprecated fisheye parameter version: 1')
            perspective_points = data['points']
            self.fisheye_param = {
                'k': np.array(data['k']),
                'd': np.array(data['d']),
                'perspective_points': np.array(perspective_points),
            }
            if self.camera_3d_rotation:
                self.apply_3d_rotaion_to_perspective_points()
        elif version == 2:
            self.fisheye_param = {
                'v': version,
                'k': np.array(data['k']),
                'd': np.array(data['d']),
                'ref_height': data['refHeight'],
                'rvec_polyfit': np.array(data['rvec_polyfit']),
                'tvec_polyfit': np.array(data['tvec_polyfit']),
            }
        elif version == 3:
            self.fisheye_param = {
                'v': version,
                'k': np.array(data['k']),
                'd': np.array(data['d']),
                'rvec': np.array(data['rvec']),
                'tvec': np.array(data['tvec']),
            }
        elif version == 4:
            self.fisheye_param = {
                'v': version,
                'k': np.array(data['k']),
                'd': np.array(data['d']),
                'rvec_polyfits': data['rvec_polyfits'],
                'tvec_polyfits': data['tvec_polyfits'],
                'grids': data['grids'],
            }
        else:
            self.send_error('Invalid version')
            return
        self.send_ok()

    def set_leveling_data(self, data):
        data = json.loads(data)
        self.leveling_data = data
        self.send_ok()

    def set_fisheye_height(self, h, model_name):
        if not self.fisheye_param:
            self.send_error('Invalid version')
            return
        version = self.fisheye_param.get('v', 1)
        if version == 2:
            k = self.fisheye_param['k']
            d = self.fisheye_param['d']
            rvec_polyfit = self.fisheye_param['rvec_polyfit']
            tvec_polyfit = self.fisheye_param['tvec_polyfit']
            dh = h - self.fisheye_param['ref_height']
            X = np.array([dh, 1])
            rvec = np.dot(X, rvec_polyfit)
            tvec = np.dot(X, tvec_polyfit)
            hw_profile = HW_PROFILE.get(model_name, {'width': 430, 'length': 320})
            width, height = hw_profile['width'], hw_profile['length']
            xgrid, ygrid = range(0, width + 1, 10), range(0, height + 1, 10)
            objp = np.zeros((len(xgrid) * len(ygrid), 1, 3), np.float64)
            keyMap = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I']
            for i in range(len(ygrid)):
                for j in range(len(xgrid)):
                    h = dh
                    if self.leveling_data is not None:
                        x = min(int((xgrid[j] / width) * 3), 2)
                        y = min(int((ygrid[i] / height) * 3), 2)
                        key = keyMap[y * 3 + x]
                        h -= self.leveling_data[key]
                    objp[i * len(xgrid) + j] = [xgrid[j], ygrid[i], -h]
            projected_points, _ = cv2.fisheye.projectPoints(objp, rvec, tvec, k, d)
            perspective_points = remap_corners(projected_points, k, d).reshape(len(ygrid), len(xgrid), 2)
            self.fisheye_param.update({'xgrid': xgrid, 'ygrid': ygrid, 'perspective_points': perspective_points})
        elif version == 4:
            k = self.fisheye_param['k']
            d = self.fisheye_param['d']
            rvec_polyfits = self.fisheye_param['rvec_polyfits']
            tvec_polyfits = self.fisheye_param['tvec_polyfits']
            rvecs = {}
            tvecs = {}
            X = np.array([h, 1])
            for key in rvec_polyfits.keys():
                rvec = np.dot(X, rvec_polyfits[key])
                tvec = np.dot(X, tvec_polyfits[key])
                rvecs[key] = rvec
                tvecs[key] = tvec
            grids = self.fisheye_param['grids']
            xgrid, ygrid, objp = generate_grid_objects(grids['x'], grids['y'])
            orig_shape = objp.shape
            objp = objp.reshape(-1, 3)
            perspective_points = np.zeros((objp.shape[0], 2), np.float32)
            region_key_map = ['topLeft', 'top', 'topRight', 'left', 'center', 'right', 'bottomLeft', 'bottom', 'bottomRight']
            for i in range(objp.shape[0]):
                x, y = objp[i][0], objp[i][1]
                x_index = min(int((x - xgrid[0]) * 3 // (xgrid[-1] - xgrid[0])), 2)
                y_index = min(int((y - ygrid[0]) * 3 // (ygrid[-1] - ygrid[0])), 2)
                region = region_key_map[y_index * 3 + x_index]
                rvec = rvecs[region]
                tvec = tvecs[region]
                point, _ = cv2.fisheye.projectPoints(np.array([[x, y, -h]]).reshape(-1, 1, 3).astype(np.float32), rvec, tvec, k, d)
                perspective_points[i] = point[0][0]
            perspective_points = perspective_points.reshape(1, -1, 2)
            perspective_points = remap_corners(perspective_points, k, d).reshape(orig_shape[0], orig_shape[1], 2)
            self.fisheye_param.update({
                'xgrid': xgrid - xgrid[0],
                'ygrid': ygrid - ygrid[0],
                'perspective_points': perspective_points,
            })

        else:
            self.send_error('Invalid version')
            return
        self.send_ok()

    def set_fisheye_grid(self, data):
        data = json.loads(data)
        if not self.fisheye_param or self.fisheye_param.get('v', 1) != 3:
            self.send_error('Invalid version')
            return
        xgrid, ygrid, objp = generate_grid_objects(data['x'], data['y'])
        k = self.fisheye_param['k']
        d = self.fisheye_param['d']
        rvec = self.fisheye_param['rvec']
        tvec = self.fisheye_param['tvec']
        points, _ = cv2.fisheye.projectPoints(objp.reshape(-1, 1, 3).astype(np.float32), rvec, tvec, k, d)
        points = remap_corners(points, k, d).reshape(objp.shape[0], objp.shape[1], 2)
        self.fisheye_param.update({'xgrid': xgrid - xgrid[0], 'ygrid': ygrid - ygrid[0], 'perspective_points': points})
        self.send_ok()

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
                CHESSBOARD,
                perspective_points,
                downsample=downsample,
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
        elif version == 2 or version == 3 or version == 4:
            k = self.fisheye_param['k']
            d = self.fisheye_param['d']
            xgrid = self.fisheye_param['xgrid']
            ygrid = self.fisheye_param['ygrid']
            img = pad_image(open_cv_img, (0, 0, 0))
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
            padding = 150 if version == 2 else 0
            img = apply_points(img, self.fisheye_param['perspective_points'], xgrid, ygrid, padding=padding)
            img = img[padding:, padding:]
        return img
