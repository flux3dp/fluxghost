"""Unit check for the OOM downsample fallback in camera.py on_image.

On low-memory devices cv2 raises during full-resolution fisheye processing;
on_image must retry the frame at increasing downsample (sticky for the
connection) and drop the frame only past downsample 4.
"""

import io
import unittest

import cv2
import numpy as np
from PIL import Image

from fluxghost.api.camera import camera_api_mixin

CameraAPI = camera_api_mixin(object)


def make_frame():
    buf = io.BytesIO()
    Image.new('RGBA', (8, 8)).save(buf, 'PNG')
    return buf.getvalue()


def make_api(fail_below):
    api = object.__new__(CameraAPI)
    api.remote_model = 'ado1'
    api.fisheye_param = {}
    api.sent = []
    api.send_binary = api.sent.append
    api.downsamples_tried = []

    def fake_handle(cv_img, downsample=1, is_low_resolution=False):
        api.downsamples_tried.append(downsample)
        if downsample < fail_below:
            # numpy raises MemoryError, cv2 raises cv2.error; both must be caught
            raise MemoryError() if downsample % 4 == 2 else cv2.error('out of memory')
        return np.zeros((4, 4, 3), np.uint8)

    api.handle_fisheye_image = fake_handle
    return api


class TestCameraOomFallback(unittest.TestCase):
    def test_retries_downsampled_and_sticks(self):
        api = make_api(fail_below=2)
        api.on_image(None, make_frame())
        self.assertEqual(api.downsamples_tried, [1, 2])
        self.assertEqual(len(api.sent), 1)
        # next frame goes straight to the working downsample
        api.on_image(None, make_frame())
        self.assertEqual(api.downsamples_tried, [1, 2, 2])
        self.assertEqual(len(api.sent), 2)

    def test_gives_up_past_downsample_4(self):
        api = make_api(fail_below=100)
        api.on_image(None, make_frame())
        self.assertEqual(api.downsamples_tried, [1, 2, 4])
        self.assertEqual(api.sent, [])  # frame dropped, nothing sent


if __name__ == '__main__':
    unittest.main()
