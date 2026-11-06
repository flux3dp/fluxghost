"""`set_pose_check` and the `{"status": "frame", "pose": ...}` message on the camera endpoint.

Hardware-free: the API object is built as in test_camera_oom_fallback.py, the v4 parameters describe a pinhole
camera looking straight down at a 300x200 mm bed, and the frame is the open-lid fixture of test_pose_check.py.
Spec: beam-studio docs/prd/auto-full-area-preview-pose-check.md §7.2.
"""

import io
import json
import os
import unittest

import cv2
import numpy as np
from PIL import Image

from fluxclient.utils.version import StrictVersion
from fluxghost.api.api_base import ApiBase
from fluxghost.api.camera import camera_api_mixin
from tests.usage.test_pose_check import FIXTURES, OPEN_RIMS

CameraAPI = camera_api_mixin(ApiBase)  # ApiBase for send_ok / send_error / send_json on top of send_text

REGIONS = ['topLeft', 'top', 'topRight', 'left', 'center', 'right', 'bottomLeft', 'bottom', 'bottomRight']
# Degree-1 polyfits against height: [[slope], [value at h = 0]] per component
ZERO_ROT = [[0.0, 0.0, 0.0], [0.0, 0.0, 0.0]]
STRAIGHT_DOWN = [[0.0, 0.0, -1.0], [0.0, 0.0, 300.0]]  # 300 mm above the bed, one mm closer per mm of height
V4_PARAMS = {
    'v': 4,
    'k': [[1000.0, 0.0, 640.0], [0.0, 1000.0, 480.0], [0.0, 0.0, 1.0]],
    'd': [[0.0], [0.0], [0.0], [0.0], [0.0]],
    'is_fisheye': False,
    'rvec_polyfits': {r: ZERO_ROT for r in REGIONS},
    'tvec_polyfits': {r: STRAIGHT_DOWN for r in REGIONS},
    'grids': {'x': [0, 300, 10], 'y': [0, 200, 10]},
}


def open_frame_jpeg():
    with open(os.path.join(FIXTURES, 'open.jpg'), 'rb') as f:
        return f.read()


def make_api():
    api = object.__new__(CameraAPI)
    api.remote_model = 'fhx2rf'
    api.remote_version = StrictVersion('5.0.0')  # on_command ignores every command on firmware <= 1.0
    api.reset_params()
    api.sent = []  # text and binary messages in order
    api.send_text = lambda text: api.sent.append(json.loads(text))
    api.send_binary = lambda buf: api.sent.append(b'<frame>')
    api.handle_fisheye_image = lambda cv_img, downsample=1, is_low_resolution=False: np.zeros((4, 4, 3), np.uint8)
    return api


class SetLidCheckTest(unittest.TestCase):
    def test_needs_v4_extrinsics(self):
        api = make_api()
        api.on_command('set_pose_check {"enabled": true}')
        self.assertEqual(api.sent[-1], {'status': 'error', 'error': ['No fisheye params']})
        self.assertIsNone(api.pose_check)

    def test_enables_with_expected_rims_from_the_calibration(self):
        api = make_api()
        api.on_command('set_fisheye_matrix ' + json.dumps(V4_PARAMS))
        self.assertEqual(api.sent[-1], {'status': 'ok'})
        api.on_command('set_pose_check {"enabled": true, "tolerance_deg": 2}')
        self.assertEqual(api.sent[-1], {'status': 'ok'})
        self.assertEqual(api.pose_check, {'tolerance': 2.0})
        # straight-down pinhole: both bed edges vertical, x = 0 at cx, x = 300 mm one bed width to the right
        expected = api.compute_expected_rims()
        self.assertAlmostEqual(expected['left']['deg'], 0.0, places=3)
        self.assertAlmostEqual(expected['left']['b'], 640.0, places=1)
        self.assertAlmostEqual(expected['right']['b'], 1640.0, places=1)

    def test_expected_rims_follow_the_current_height(self):
        api = make_api()
        api.on_command('set_fisheye_matrix ' + json.dumps(V4_PARAMS))
        api.on_command('set_pose_check {"enabled": true}')
        self.assertAlmostEqual(api.compute_expected_rims()['right']['b'], 1640.0, places=1)
        api.on_command('set_fisheye_height 150')  # camera 150 mm closer: the right edge projects further out
        self.assertAlmostEqual(api.compute_expected_rims()['right']['b'], 2640.0, places=1)

    def test_disable(self):
        api = make_api()
        api.on_command('set_fisheye_matrix ' + json.dumps(V4_PARAMS))
        api.on_command('set_pose_check {"enabled": true}')
        api.on_command('set_pose_check {"enabled": false}')
        self.assertEqual(api.sent[-1], {'status': 'ok'})
        self.assertIsNone(api.pose_check)


class FrameMessageTest(unittest.TestCase):
    def test_no_message_unless_enabled(self):
        api = make_api()
        api.on_command('set_fisheye_matrix ' + json.dumps(V4_PARAMS))
        del api.sent[:]
        api.on_image(None, open_frame_jpeg())
        self.assertEqual(api.sent, [b'<frame>'])

    def test_frame_message_precedes_the_frame(self):
        api = make_api()
        api.on_command('set_fisheye_matrix ' + json.dumps(V4_PARAMS))
        api.on_command('set_pose_check {"enabled": true}')
        api.compute_expected_rims = lambda: OPEN_RIMS  # the fixture's own rims; the pinhole set does not match it
        del api.sent[:]
        api.on_image(None, open_frame_jpeg())
        self.assertEqual(len(api.sent), 2)
        self.assertEqual(api.sent[0]['status'], 'frame')
        self.assertTrue(api.sent[0]['pose']['ok'], api.sent[0])
        self.assertAlmostEqual(api.sent[0]['pose']['left'], 2.0, delta=0.5)
        self.assertEqual(api.sent[1], b'<frame>')

    def test_rims_not_found_reports_ok_false(self):
        api = make_api()
        api.on_command('set_fisheye_matrix ' + json.dumps(V4_PARAMS))
        api.on_command('set_pose_check {"enabled": true}')
        del api.sent[:]
        buf = io.BytesIO()
        Image.fromarray(np.zeros((480, 640, 3), np.uint8)).save(buf, 'JPEG')
        api.on_image(None, buf.getvalue())
        self.assertEqual(
            api.sent[0]['pose'],
            {
                'ok': False,
                'left': None,
                'right': None,
                'expected_left': 0.0,
                'expected_right': 0.0,
            },
        )

    def test_parameters_without_extrinsics_report_nothing_to_compare(self):
        api = make_api()
        api.on_command('set_fisheye_matrix ' + json.dumps(V4_PARAMS))
        api.on_command('set_pose_check {"enabled": true}')
        # v3 is fisheye-only in set_fisheye_grid (remap_corners): four distortion terms, as the smoke suite sends
        v3 = {
            'v': 3,
            'k': V4_PARAMS['k'],
            'd': [[0.0], [0.0], [0.0], [0.0]],
            'rvec': [[0.0], [0.0], [0.0]],
            'tvec': [[0.0], [0.0], [300.0]],
        }
        api.on_command('set_fisheye_matrix ' + json.dumps(v3))
        api.on_command('set_fisheye_grid {"x": [0, 30, 10], "y": [0, 30, 10]}')
        del api.sent[:]
        api.on_image(None, open_frame_jpeg())
        self.assertEqual(
            api.sent[0]['pose'],
            {
                'ok': False,
                'left': None,
                'right': None,
                'expected_left': None,
                'expected_right': None,
            },
        )
        self.assertEqual(api.sent[1], b'<frame>')

    def test_a_failing_check_disables_itself_and_still_sends_the_frame(self):
        api = make_api()
        api.on_command('set_fisheye_matrix ' + json.dumps(V4_PARAMS))
        api.on_command('set_pose_check {"enabled": true}')
        api.compute_expected_rims = lambda: {'left': {}, 'right': {}}  # malformed: measure_rims raises KeyError
        del api.sent[:]
        api.on_image(None, open_frame_jpeg())
        self.assertEqual(api.sent, [b'<frame>'])
        self.assertIsNone(api.pose_check)


if __name__ == '__main__':
    unittest.main()
