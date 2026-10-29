"""The device tags an upside-down camera's frames with EXIF Orientation=3 instead
of rotating the pixels (HEXA II galvo head). Every endpoint that works on camera
pixels must apply that tag, or the calibration (k, d, rvec, tvec) ends up
computed on a 180-rotated frame while the browser -- and the device's own
consumers -- show it upright.

Checks `open_frame` itself, the preview path (camera.py on_image), and that no
api module decodes an upload behind open_frame's back.
"""

import io
import pathlib
import unittest

import numpy as np
from PIL import Image

from fluxghost.api.camera import camera_api_mixin
from fluxghost.utils.camera.general import open_frame

CameraAPI = camera_api_mixin(object)

API_DIR = pathlib.Path(__file__).resolve().parents[2] / 'fluxghost' / 'api'
FRAME_DECODERS = ['camera.py', 'camera_calibration.py', 'camera_transform.py', 'opencv.py']


def asymmetric_pixels():
    # Top-left pixel red, everything else black: rotating it 180 is visible.
    arr = np.zeros((6, 8, 3), np.uint8)
    arr[0, 0] = (255, 0, 0)
    return arr


def jpeg(arr, orientation=None):
    """Lossless-enough JPEG (quality 100) of arr, optionally EXIF-tagged."""
    buf = io.BytesIO()
    kwargs = {'quality': 100, 'subsampling': 0}
    if orientation is not None:
        exif = Image.Exif()
        exif[0x0112] = orientation
        kwargs['exif'] = exif.tobytes()
    Image.fromarray(arr).save(buf, 'JPEG', **kwargs)
    return buf.getvalue()


def red_at(arr):
    ys, xs = np.where(arr[:, :, 0] > 128)
    return int(ys[0]), int(xs[0])


class OpenFrameTest(unittest.TestCase):
    def test_untagged_frame_is_left_alone(self):
        arr = np.array(open_frame(jpeg(asymmetric_pixels())))
        self.assertEqual(arr.shape, (6, 8, 3))
        self.assertEqual(red_at(arr), (0, 0))

    def test_orientation_3_rotates_180(self):
        arr = np.array(open_frame(jpeg(asymmetric_pixels(), orientation=3)))
        self.assertEqual(arr.shape, (6, 8, 3))
        self.assertEqual(red_at(arr), (5, 7))

    def test_png_without_exif_is_unchanged(self):
        buf = io.BytesIO()
        Image.fromarray(asymmetric_pixels()).save(buf, 'PNG')
        arr = np.array(open_frame(buf.getvalue()))
        self.assertEqual(red_at(arr), (0, 0))


class PreviewPathTest(unittest.TestCase):
    def make_api(self):
        api = object.__new__(CameraAPI)
        api.remote_model = 'fhx2galvo'
        api.fisheye_param = {}
        api.preview_downsample = 1
        api.is_next_image_low_resolution = False
        api.next_image_dpmm = None
        api.sent = []
        api.send_binary = api.sent.append
        api.frames = []

        def fake_handle(cv_img, **kwargs):
            api.frames.append(cv_img)
            return np.zeros((4, 4, 3), np.uint8)

        api.handle_fisheye_image = fake_handle
        return api

    def test_fisheye_preview_sees_the_upright_frame(self):
        api = self.make_api()
        api.on_image(None, jpeg(asymmetric_pixels(), orientation=3))
        self.assertEqual(len(api.frames), 1)
        bgr = api.frames[0]
        ys, xs = np.where(bgr[:, :, 2] > 128)  # BGR: red is channel 2
        self.assertEqual((int(ys[0]), int(xs[0])), (5, 7))
        self.assertEqual(len(api.sent), 1)


class NoBareDecodeTest(unittest.TestCase):
    def test_frame_consumers_decode_through_open_frame(self):
        for name in FRAME_DECODERS:
            source = (API_DIR / name).read_text()
            self.assertNotIn('Image.open(', source, '%s decodes a frame without open_frame' % name)
            self.assertNotIn('cv2.imdecode(', source, '%s decodes a frame without open_frame' % name)
            self.assertIn('open_frame(', source, '%s should decode uploads with open_frame' % name)


if __name__ == '__main__':
    unittest.main()
