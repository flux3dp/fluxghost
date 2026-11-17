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
from fluxghost.utils.camera.constants import IMAGE_H, IMAGE_W, L_PAD, T_PAD

FIXTURES = os.path.join(os.path.dirname(__file__), 'fixtures', 'pose_check')

# Pinhole (is_fisheye=False): under the equidistant fisheye model even D = 0 bends an off-centre edge into an arc
K = np.array([[1000.0, 0.0, 640.0], [0.0, 1000.0, 480.0], [0.0, 0.0, 1.0]])
D = np.zeros((5, 1))
TVEC = np.array([[0.0], [0.0], [300.0]])


def line_rim(deg, a, b, scale=1.0):
    """An `expected_rims` entry for the straight line x = a*y + b (analysis pixels), scaled to the frame."""
    ys = np.array([0.0, 2000.0])
    return {'deg': deg, 'xs': (a * ys + b) * scale, 'ys': ys * scale}


# Fitted on open.jpg (fhx2rf, lid at its stop): left rim +2.0 deg, right rim -2.0 deg
OPEN_LINES = {'left': (1.98, 0.0346, 101.1), 'right': (-1.96, -0.0343, 1149.1)}
OPEN_RIMS = {side: line_rim(*line) for side, line in OPEN_LINES.items()}


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
        self.assertAlmostEqual(rims['left']['xs'][0], 640.0, places=1)
        self.assertAlmostEqual(rims['right']['xs'][0], 1640.0, places=1)

    def test_fisheye_rims_come_back_in_raw_frame_pixels(self):
        # calibrate_fisheye_camera pads each frame by (L_PAD, T_PAD) before solving, so a fisheye K's principal
        # point is in padded coordinates. A camera straight above the bed centre must still put the rims
        # symmetrically about the raw frame's centre column, not about the padded one.
        k = np.array([[1000.0, 0.0, IMAGE_W / 2 + L_PAD], [0.0, 1000.0, IMAGE_H / 2 + T_PAD], [0.0, 0.0, 1.0]])
        d = np.zeros((4, 1))
        rvec = np.zeros((3, 1))
        tvec = np.array([[-150.0], [-100.0], [300.0]])
        rims = pose_check.expected_rims(k, d, {'left': rvec, 'right': rvec}, {'left': tvec, 'right': tvec}, 300, 200)
        self.assertAlmostEqual((rims['left']['xs'][0] + rims['right']['xs'][0]) / 2, IMAGE_W / 2, places=1)
        self.assertLess(rims['left']['xs'][0], IMAGE_W / 2)
        self.assertAlmostEqual(rims['left']['deg'], 0.0, places=3)

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
        # The same lines in full-resolution pixels: the band around them is met after downscaling ...
        rims = {side: line_rim(*line, scale=2) for side, line in OPEN_LINES.items()}
        result = pose_check.measure_rims(big, rims)
        self.assertIsNotNone(result['left'], result)
        self.assertIsNotNone(result['right'], result)
        # ... and the right rim (expected at x = 1149 of 2560 after halving: the middle of the bed) is missed when
        # the intercept is left in analysis pixels. The left one is not a check: half of 101 is still near x = 108.
        result = pose_check.measure_rims(big, OPEN_RIMS)
        self.assertIsNone(result['right'], result)

    def test_curved_rims_compare_against_the_curve_where_the_segment_is(self):
        # A bent rim's straight fit is several degrees off any stretch of it, so a segment is judged against the
        # curve's own chord over its rows
        ys = np.arange(0.0, 961.0, 10.0)
        left = 150 + 0.0002 * ys**2
        img = np.zeros((960, 1280), np.uint8)
        for xs in (left, 1280 - left):
            cv2.polylines(img, [np.stack([xs, ys], axis=1).astype(np.int32)], False, 255, 3)
        rims = {
            side: {'deg': pose_check.fit_line(np.stack([xs, ys], axis=1))[0], 'xs': xs, 'ys': ys}
            for side, xs in (('left', left), ('right', 1280 - left))
        }
        result = pose_check.measure_rims(img, rims)
        self.assertTrue(result['ok'], result)
        self.assertGreater(abs(result['left'] - rims['left']['deg']), pose_check.DEFAULT_TOLERANCE_DEG)

    def test_tolerance_is_applied_per_rim(self):
        result = pose_check.measure_rims(fixture('open'), OPEN_RIMS, tolerance_deg=0.01)
        self.assertFalse(result['ok'], result)


def ridge_frame(xs, ys, w=3264, h=2448):
    """Dark full-resolution frame with a 2 px bright line along (xs, ys), like the LED highlight on fbb2's chassis."""
    img = np.full((h, w), 10, np.uint8)
    cv2.polylines(img, [np.stack([xs, ys], axis=1).astype(np.int32)], False, 200, 2)
    return img


class MeasureRidgesTest(unittest.TestCase):
    ys = np.arange(1000.0, 2400.0, 10.0)
    left = 300 + 0.0003 * (ys - 1000) ** 2
    right = 3264 - left
    rims = {'left': {'deg': 0.0, 'xs': left, 'ys': ys}, 'right': {'deg': 0.0, 'xs': right, 'ys': ys}}

    def test_highlight_on_both_curves_passes(self):
        img = np.maximum(ridge_frame(self.left, self.ys), ridge_frame(self.right, self.ys))
        result = pose_check.measure_ridges(img, self.rims)
        self.assertTrue(result['ok'], result)
        self.assertGreater(result['left'], pose_check.RIDGE_MIN)
        self.assertEqual(result['expected_left'], pose_check.RIDGE_MIN)

    def test_one_side_is_enough(self):
        # the highlight is specular: at the open stop one side can go dark
        result = pose_check.measure_ridges(ridge_frame(self.left, self.ys), self.rims)
        self.assertTrue(result['ok'], result)
        self.assertLess(result['right'], pose_check.RIDGE_MIN)

    def test_highlight_off_the_curve_fails(self):
        # a lowered lid moves the chassis edge well past the search window (20 px vanished on the fbb2 frames)
        img = np.maximum(ridge_frame(self.left + 20, self.ys), ridge_frame(self.right - 20, self.ys))
        result = pose_check.measure_ridges(img, self.rims)
        self.assertFalse(result['ok'], result)
        self.assertLess(result['left'], 1.0)

    def test_curve_mostly_outside_the_frame_scores_zero(self):
        rims = {s: {'deg': 0.0, 'xs': r['xs'] + 5000, 'ys': r['ys']} for s, r in self.rims.items()}
        result = pose_check.measure_ridges(ridge_frame(self.left, self.ys), rims)
        self.assertEqual((result['ok'], result['left'], result['right']), (False, 0.0, 0.0))


if __name__ == '__main__':
    unittest.main()
