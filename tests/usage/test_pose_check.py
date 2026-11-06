"""Unit checks for fluxghost/utils/camera/pose_check.py (beam-studio docs/prd/auto-full-area-preview-pose-check.md §13).

`expected_rims` is checked against a synthetic pinhole camera where the answer is analytic; `measure_rims`
against four 1280-px frames cut from the fhx2rf study dump of 2026-11-06, with the expected lines fitted on the
open frame (the real reference comes from the calibration, see the mixin).
"""

import os
import unittest

import cv2
import numpy as np

from fluxghost.utils.camera import pose_check

FIXTURES = os.path.join(os.path.dirname(__file__), 'fixtures', 'pose_check')

# Pinhole (is_fisheye=False): under the equidistant fisheye model even D = 0 bends an off-centre edge into an arc
K = np.array([[1000.0, 0.0, 640.0], [0.0, 1000.0, 480.0], [0.0, 0.0, 1.0]])
D = np.zeros((5, 1))
TVEC = np.array([[0.0], [0.0], [300.0]])

# Fitted on open.jpg (fhx2rf, lid at its stop): left rim +2.0 deg, right rim -2.0 deg
OPEN_RIMS = {
    'left': {'deg': 1.98, 'a': 0.0346, 'b': 101.1},
    'right': {'deg': -1.96, 'a': -0.0343, 'b': 1149.1},
}


def fixture(name):
    img = cv2.imread(os.path.join(FIXTURES, name + '.jpg'))
    assert img is not None, name
    return img


class ExpectedRimsTest(unittest.TestCase):
    def test_straight_down_camera_gives_vertical_rims_at_the_bed_edges(self):
        rvec = np.zeros((3, 1))
        rims = pose_check.expected_rims(
            K, D, {'left': rvec, 'right': rvec}, {'left': TVEC, 'right': TVEC}, 300, 200, is_fisheye=False
        )
        self.assertAlmostEqual(rims['left']['deg'], 0.0, places=3)
        self.assertAlmostEqual(rims['right']['deg'], 0.0, places=3)
        # u = fx * x / z + cx: x = 0 -> 640, x = 300 at z = 300 -> 1640
        self.assertAlmostEqual(rims['left']['b'], 640.0, places=1)
        self.assertAlmostEqual(rims['right']['b'], 1640.0, places=1)

    def test_pitched_camera_converges_the_rims_symmetrically(self):
        # Pitch about the bed's x axis (the hinge direction): both edges tilt, mirror images of each other
        rvec = np.array([[np.radians(15.0)], [0.0], [0.0]])
        tvec = np.array([[-150.0], [-100.0], [300.0]])
        rims = pose_check.expected_rims(
            K, D, {'left': rvec, 'right': rvec}, {'left': tvec, 'right': tvec}, 300, 200, is_fisheye=False
        )
        self.assertGreater(abs(rims['left']['deg']), 1.0)
        self.assertAlmostEqual(rims['left']['deg'], -rims['right']['deg'], places=3)


class MeasureRimsTest(unittest.TestCase):
    def test_open_lid_passes(self):
        result = pose_check.measure_rims(fixture('open'), OPEN_RIMS)
        self.assertTrue(result['ok'], result)
        self.assertAlmostEqual(result['left'], 2.0, delta=0.5)
        self.assertAlmostEqual(result['right'], -2.0, delta=0.5)
        self.assertEqual(result['expected_left'], 2.0)

    def test_small_tilt_is_rejected_on_angle(self):
        result = pose_check.measure_rims(fixture('tilt-small'), OPEN_RIMS)
        self.assertFalse(result['ok'], result)
        # both rims found, both turned past vertical the other way
        self.assertLess(result['left'], -2.0)
        self.assertGreater(result['right'], 1.0)

    def test_nearly_shut_lid_has_no_rims(self):
        result = pose_check.measure_rims(fixture('nearly-shut'), OPEN_RIMS)
        self.assertFalse(result['ok'], result)
        self.assertIsNone(result['left'])
        self.assertIsNone(result['right'])

    def test_closing_blur_is_the_known_gap(self):
        # A frame shot while the lid moves can still read within tolerance: the angle test alone does not
        # catch motion blur (PRD open decision 2). Pinned here so a blur gate shows up as a change.
        result = pose_check.measure_rims(fixture('closing-blur'), OPEN_RIMS)
        self.assertIsNotNone(result['left'])
        self.assertIsNotNone(result['right'])

    def test_expected_lines_are_in_full_resolution_pixels(self):
        img = fixture('open')
        big = cv2.resize(img, (img.shape[1] * 2, img.shape[0] * 2), interpolation=cv2.INTER_LINEAR)
        # Same slope, intercept doubled: the band around the expected line is met after downscaling ...
        rims = {s: {'deg': r['deg'], 'a': r['a'], 'b': r['b'] * 2} for s, r in OPEN_RIMS.items()}
        result = pose_check.measure_rims(big, rims)
        self.assertIsNotNone(result['left'], result)
        self.assertIsNotNone(result['right'], result)
        # ... and the right rim (expected at x = 1149 of 2560 after halving: the middle of the bed) is missed when
        # the intercept is left in analysis pixels. The left one is not a check: half of 101 is still near x = 108.
        result = pose_check.measure_rims(big, OPEN_RIMS)
        self.assertIsNone(result['right'], result)

    def test_tolerance_is_applied_per_rim(self):
        result = pose_check.measure_rims(fixture('open'), OPEN_RIMS, tolerance_deg=0.01)
        self.assertFalse(result['ok'], result)


if __name__ == '__main__':
    unittest.main()
