"""Unit check for the cached fixed-point undistort maps in
fluxghost/utils/camera/calibration.py (get_remap_img).

The cache was added because rebuilding two full-resolution CV_32FC1 maps per
preview frame OOM'd low-memory devices. This verifies the cached CV_16SC2
path stays numerically equivalent to the original per-call float-map code.
"""

import unittest

import cv2
import numpy as np

from fluxghost.utils.camera import calibration
from fluxghost.utils.camera.calibration import get_remap_img

K = np.array([[300.0, 0, 160], [0, 300.0, 120], [0, 0, 1]])
D_FISHEYE = np.array([[0.0], [0.1], [0.05], [-0.1]])
D_PLAIN = np.array([0.1, -0.05, 0.001, 0.001, 0.0])


def synth_img():
    # Smooth gradients: a geometry error shows up as a large diff, while the
    # fixed-point maps' 1/32-px coordinate quantization stays within ~1 level
    xx, yy = np.meshgrid(np.linspace(0, 255, 320), np.linspace(0, 255, 240))
    return np.dstack([xx, yy, (xx + yy) / 2]).astype(np.uint8)


class TestRemapCache(unittest.TestCase):
    def setUp(self):
        calibration._remap_map_cache.clear()

    def test_fisheye_matches_uncached_float_maps(self):
        img = synth_img()
        h, w = img.shape[:2]
        mapx, mapy = cv2.fisheye.initUndistortRectifyMap(K, D_FISHEYE, np.eye(3), K, (w, h), cv2.CV_32FC1)
        expected = cv2.remap(img, mapx, mapy, cv2.INTER_LINEAR)
        got = get_remap_img(img, K, D_FISHEYE, is_fisheye=True)
        # CV_16SC2 fixed-point maps quantize interpolation weights slightly
        self.assertLessEqual(int(np.abs(expected.astype(int) - got.astype(int)).max()), 2)

    def test_plain_matches_cv2_undistort(self):
        img = synth_img()
        expected = cv2.undistort(img, K, D_PLAIN)
        got = get_remap_img(img, K, D_PLAIN, is_fisheye=False)
        diff = np.abs(expected.astype(int) - got.astype(int))
        # cv2.undistort computes its maps in double precision, initUndistortRectifyMap
        # in float; a handful of isolated pixels differ by a few levels
        self.assertLessEqual(float(np.percentile(diff, 99.9)), 1)
        self.assertLessEqual(int(diff.max()), 16)

    def test_maps_are_cached_and_reused(self):
        img = synth_img()
        get_remap_img(img, K, D_FISHEYE)
        self.assertEqual(len(calibration._remap_map_cache), 1)
        maps_before = next(iter(calibration._remap_map_cache.values()))
        get_remap_img(img, K, D_FISHEYE)
        self.assertIs(next(iter(calibration._remap_map_cache.values())), maps_before)
        # A different size evicts the old entry (single-entry cache)
        get_remap_img(img[:120, :160], K, D_FISHEYE)
        self.assertEqual(len(calibration._remap_map_cache), 1)
        self.assertIsNot(next(iter(calibration._remap_map_cache.values())), maps_before)


if __name__ == '__main__':
    unittest.main()
