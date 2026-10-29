"""Frames asked for at an explicit px/mm (`require_frame d<dpmm>`, the galvo
calibration capture) are kept on disk as they came from the device and as they
went back to the client, so a failed solve can be traced to the photographs.
Plain previews are not kept.
"""

import io
import json
import os
import pathlib
import tempfile
import unittest

import numpy as np
from PIL import Image

from fluxghost.api.camera import camera_api_mixin
from fluxghost.utils.camera import frame_dump
from fluxghost.utils.camera.frame_dump import FrameDump

CameraAPI = camera_api_mixin(object)


def jpeg(value):
    arr = np.full((4, 4, 3), value, np.uint8)
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, 'JPEG')
    return buf.getvalue()


class FrameDumpTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_writes_raw_and_remap_numbered_in_one_folder(self):
        dump = FrameDump(enabled=True, root=str(self.root))
        folder = dump.save(b'raw1', b'remap1', dpmm=20)
        self.assertEqual(dump.save(b'raw2', b'remap2', dpmm=20), folder)
        names = sorted(os.listdir(folder))
        self.assertEqual(names, ['01-raw.jpg', '01-remap-20ppm.jpg', '02-raw.jpg', '02-remap-20ppm.jpg'])
        self.assertEqual((pathlib.Path(folder) / '02-remap-20ppm.jpg').read_bytes(), b'remap2')
        self.assertEqual(frame_dump.latest_folder(), folder)

    def test_raw_only_when_there_was_no_remap(self):
        dump = FrameDump(enabled=True, root=str(self.root))
        folder = dump.save(b'raw', None, dpmm=20)
        self.assertEqual(os.listdir(folder), ['01-raw.jpg'])

    def test_disabled_writes_nothing(self):
        dump = FrameDump(enabled=False, root=str(self.root))
        self.assertIsNone(dump.save(b'raw', b'remap', dpmm=20))
        self.assertEqual(os.listdir(self.root), [])

    def test_env_switch_and_dir(self):
        old = {k: os.environ.get(k) for k in ('FLUXGHOST_FRAME_DUMP', 'FLUXGHOST_FRAME_DUMP_DIR')}
        try:
            os.environ['FLUXGHOST_FRAME_DUMP'] = '0'
            self.assertFalse(frame_dump.is_enabled())
            os.environ['FLUXGHOST_FRAME_DUMP'] = '1'
            self.assertTrue(frame_dump.is_enabled())
            os.environ['FLUXGHOST_FRAME_DUMP_DIR'] = str(self.root / 'elsewhere')
            self.assertEqual(frame_dump.base_dir(), str(self.root / 'elsewhere'))
        finally:
            for k, v in old.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v


class SaveCaptureTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_stitched_json_and_patches_cut_from_the_saved_remaps(self):
        dump = FrameDump(enabled=True, root=str(self.root))
        # frame 1: a 10x8 remap whose pixel (x=3, y=2) is red; frame 2: all blue
        arr = np.zeros((8, 10, 3), np.uint8)
        arr[2, 3] = (255, 0, 0)
        folder = dump.save(b'raw1', _png(arr), dpmm=20)
        dump.save(b'raw2', _png(np.full((8, 10, 3), (0, 0, 255), np.uint8)), dpmm=20)
        meta = {
            'tiles': [
                {'frame': 1, 'rect': {'sx': 3, 'sy': 2, 'sw': 4, 'sh': 3}},
                {'frame': 2, 'rect': {'sx': 0, 'sy': 0, 'sw': 2, 'sh': 2}},
                {'frame': None, 'rect': None},  # a tile that was left blank
            ],
            'warnings': ['tile 3 was left blank'],
        }
        written = frame_dump.save_capture(folder, b'stitched-bytes', meta)
        self.assertEqual(written, ['stitched.png', 'capture.json', '01-patch.png', '02-patch.png'])
        self.assertEqual((pathlib.Path(folder) / 'stitched.png').read_bytes(), b'stitched-bytes')
        with open(pathlib.Path(folder) / 'capture.json') as f:
            self.assertEqual(json.load(f)['warnings'], ['tile 3 was left blank'])
        patch = np.array(Image.open(pathlib.Path(folder) / '01-patch.png').convert('RGB'))
        self.assertEqual(patch.shape, (3, 4, 3))
        self.assertEqual(tuple(patch[0, 0]), (255, 0, 0))
        patch2 = np.array(Image.open(pathlib.Path(folder) / '02-patch.png').convert('RGB'))
        self.assertEqual(patch2.shape, (2, 2, 3))
        self.assertEqual(tuple(patch2[1, 1]), (0, 0, 255))


def _png(arr):
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, 'PNG')
    return buf.getvalue()


class PreviewPathTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def make_api(self):
        api = object.__new__(CameraAPI)
        api.remote_model = 'fhx2galvo'
        api.fisheye_param = {}
        api.preview_downsample = 1
        api.is_next_image_low_resolution = False
        api.next_image_dpmm = None
        api.frame_dump = FrameDump(enabled=True, root=self.root)
        api.sent = []
        api.send_binary = api.sent.append
        api.handle_fisheye_image = lambda cv_img, **kwargs: np.zeros((4, 4, 3), np.uint8)
        return api

    def test_explicit_dpmm_frame_is_kept_as_raw_and_remap(self):
        api = self.make_api()
        raw = jpeg(200)
        api.next_image_dpmm = 20
        api.on_image(None, raw)
        folder = api.frame_dump.folder
        self.assertEqual(sorted(os.listdir(folder)), ['01-raw.jpg', '01-remap-20ppm.jpg'])
        self.assertEqual((pathlib.Path(folder) / '01-raw.jpg').read_bytes(), raw)
        self.assertEqual((pathlib.Path(folder) / '01-remap-20ppm.jpg').read_bytes(), api.sent[0])

    def test_plain_preview_is_not_kept(self):
        api = self.make_api()
        api.on_image(None, jpeg(100))
        self.assertIsNone(api.frame_dump.folder)
        self.assertEqual(os.listdir(self.root), [])

    def test_frame_without_fisheye_params_is_still_kept_raw(self):
        api = self.make_api()
        api.fisheye_param = None
        api.next_image_dpmm = 20
        api.on_image(None, jpeg(50))
        self.assertEqual(os.listdir(api.frame_dump.folder), ['01-raw.jpg'])


if __name__ == '__main__':
    unittest.main()
