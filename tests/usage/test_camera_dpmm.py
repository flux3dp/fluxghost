"""Unit checks for `require_frame d<dpmm>` (camera.py) and the dpmm plumbing.

`require_frame d20` must hand `dpmm=20` to handle_fisheye_image for that one
frame only; plain `require_frame` / `require_frame l` must call it exactly as
before (no dpmm kwarg), so their output stays byte-identical. apply_points /
apply_perspective_points_transform must scale their output size with dpmm.
"""

import io
import unittest

import numpy as np
from PIL import Image

from fluxghost.api.camera import camera_api_mixin
from fluxghost.utils.camera.constants import DPMM
from fluxghost.utils.camera.corner_detection.apply_points import apply_points
from fluxghost.utils.camera.perspective import apply_perspective_points_transform

CameraAPI = camera_api_mixin(object)


def make_frame():
    buf = io.BytesIO()
    Image.new('RGBA', (8, 8)).save(buf, 'PNG')
    return buf.getvalue()


class FakeRobot:
    def __init__(self):
        self.calls = []

    def require_frame(self, low_resolution=False):
        self.calls.append(low_resolution)


def make_api():
    api = object.__new__(CameraAPI)
    api.remote_model = 'fhx2galvo'
    api.remote_version = type('V', (), {'__gt__': lambda self, other: True})()
    api.fisheye_param = {}
    api.robot = FakeRobot()
    api.sent = []
    api.send_binary = api.sent.append
    api.handle_calls = []

    def fake_handle(cv_img, **kwargs):
        api.handle_calls.append(kwargs)
        return np.zeros((4, 4, 3), np.uint8)

    api.handle_fisheye_image = fake_handle
    return api


class RequireFrameDpmmTest(unittest.TestCase):
    def test_d20_passes_dpmm_for_one_frame(self):
        api = make_api()
        api.on_command('require_frame d20')
        self.assertEqual(api.robot.calls, [False])
        api.on_image(None, make_frame())
        self.assertEqual(api.handle_calls[-1], {'downsample': 1, 'is_low_resolution': False, 'dpmm': 20})
        # the next frame is back to the default call
        api.on_command('require_frame')
        api.on_image(None, make_frame())
        self.assertEqual(api.handle_calls[-1], {'downsample': 1, 'is_low_resolution': False})
        self.assertEqual(len(api.sent), 2)

    def test_plain_and_low_resolution_unchanged(self):
        api = make_api()
        api.on_command('require_frame')
        api.on_image(None, make_frame())
        self.assertEqual(api.handle_calls[-1], {'downsample': 1, 'is_low_resolution': False})
        api.on_command('require_frame l')
        self.assertEqual(api.robot.calls, [False, True])
        api.on_image(None, make_frame())
        self.assertEqual(api.handle_calls[-1], {'downsample': 1, 'is_low_resolution': True})

    def test_bad_dpmm_argument_is_ignored(self):
        api = make_api()
        api.on_command('require_frame d0')
        api.on_command('require_frame dx')
        self.assertEqual(api.robot.calls, [False, False])
        api.on_image(None, make_frame())
        self.assertEqual(api.handle_calls[-1], {'downsample': 1, 'is_low_resolution': False})


class OutputScaleTest(unittest.TestCase):
    def test_apply_points_scales_with_dpmm(self):
        img = np.zeros((300, 400, 3), np.uint8)
        x_grid, y_grid = np.array([0, 10, 20]), np.array([0, 10])
        corners = np.array([[[10, 10], [110, 10], [210, 10]], [[10, 110], [110, 110], [210, 110]]], np.float32)
        default = apply_points(img, corners, x_grid, y_grid, padding=0)
        self.assertEqual(default.shape, (10 * DPMM, 20 * DPMM, 3))
        high = apply_points(img, corners, x_grid, y_grid, padding=0, perspective_pixel_per_mm=20)
        self.assertEqual(high.shape, (10 * 20, 20 * 20, 3))

    def test_perspective_transform_scales_with_dpmm(self):
        img = np.zeros((300, 400, 3), np.uint8)
        k = np.array([[200.0, 0, 200], [0, 200.0, 150], [0, 0, 1]])
        d = np.zeros(5)
        chessboard = (3, 2)
        points = np.array([[[10, 10], [10, 110]], [[110, 10], [110, 110]], [[210, 10], [210, 110]]], np.float32)
        default = apply_perspective_points_transform(img, k, d, (1, 1), chessboard, points, is_fisheye=False)
        self.assertEqual(default.shape, (10 * DPMM + 200, 20 * DPMM + 200, 3))
        high = apply_perspective_points_transform(img, k, d, (1, 1), chessboard, points, is_fisheye=False, dpmm=20)
        self.assertEqual(high.shape, (10 * 20 + 200, 20 * 20 + 200, 3))


if __name__ == '__main__':
    unittest.main()
