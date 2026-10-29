"""Unit tests for the galvo coupon solver (fluxghost/utils/camera/galvo_coupon.py).

No server, no hardware: a synthetic 20 px/mm coupon with a known affine is
rendered by tests/usage/galvo_coupon_synth.py and the solver must recover it
(beam-studio PRD hexa-g-galvo-calibration.md §7.8: 0.1 % on scale, 0.02 deg
on skew). The ws endpoint wrapper is covered by tools/ws_smoke.py.
"""

import unittest

import cv2
import numpy as np

from fluxghost.utils.camera.galvo_coupon import SolveError, solve_galvo_coupon
from tests.usage.galvo_coupon_synth import l_frame_vertices, render_coupon

TRUTH = {'scale_x': 1.02, 'scale_y': 0.98, 'skew_deg': 0.3, 'rot_deg': 5.0, 'offset_mm': (3.2, -1.7)}
PARAMS = {'px_per_mm': 20, 'expected_center_px': [1800, 1800], 'invert': [True, True]}


def assert_truth(test, res, truth=TRUTH):
    test.assertEqual(res['nodes_found'], 81)
    test.assertEqual(res['ruler']['vertices_used'], 8)
    test.assertLess(res['ruler']['rms_mm'], 0.05)
    test.assertAlmostEqual(res['scale_x'], truth['scale_x'], delta=0.001 * truth['scale_x'])
    test.assertAlmostEqual(res['scale_y'], truth['scale_y'], delta=0.001 * truth['scale_y'])
    test.assertAlmostEqual(res['skew_deg'], truth['skew_deg'], delta=0.02)
    test.assertAlmostEqual(res['rotation_deg'], truth['rot_deg'], delta=0.05)
    test.assertFalse(res['mirrored'])
    np.testing.assert_allclose(res['field_center_mm'], truth['offset_mm'], atol=0.05)
    test.assertLess(res['affine_rms'], 0.02)
    test.assertEqual(res['validation_affine']['count'], 8)
    test.assertEqual(res['validation_bilinear']['count'], 8)
    test.assertLess(res['validation_bilinear']['max'], 0.05)


class SolveGalvoCouponTest(unittest.TestCase):
    def test_recovers_known_affine_grayscale(self):
        """Grayscale image (no colour separation): galvo mask degrades to a brightness threshold."""
        res, annotated = solve_galvo_coupon(render_coupon(**TRUTH), dict(PARAMS, annotate=True))
        assert_truth(self, res)
        self.assertEqual(res['orientation']['source'], 'identity')
        self.assertTrue(res['orientation']['matches_invert'])
        self.assertEqual(res['ruler']['threshold'], ['guided', 1.0])
        self.assertEqual(res['ruler']['model'], 'affine')
        self.assertEqual(annotated.shape, (3600, 3600, 3))

    def test_recovers_known_affine_colour(self):
        """Reddish L frame (green < 150) is skipped by the first threshold set and caught by [160, 'red']."""
        res, annotated = solve_galvo_coupon(render_coupon(color=True, **TRUTH), dict(PARAMS, guided=False))
        assert_truth(self, res)
        self.assertEqual(res['ruler']['threshold'], [160, 'red'])
        self.assertIsNone(annotated)

    def test_ruler_uses_full_frame_transform(self):
        """A rotated, anisotropic ruler must not leak into scale/skew (full A^-1, not per-axis px/mm)."""
        img = render_coupon(frame_rot_deg=2.0, frame_px_per_mm=(19.6, 20.3), **TRUTH)
        res, _ = solve_galvo_coupon(img, PARAMS)
        assert_truth(self, res)
        self.assertAlmostEqual(res['ruler']['px_per_mm_x'], 19.6, delta=0.02)
        self.assertAlmostEqual(res['ruler']['px_per_mm_y'], 20.3, delta=0.02)

    def test_tolerates_noise_and_wrong_expected_center(self):
        img = render_coupon(center_px=(1960, 1700), noise=25, **TRUTH)
        res, _ = solve_galvo_coupon(img, PARAMS)  # expected_center_px is 8 mm off
        assert_truth(self, res)

    def test_identity_ring_fixes_orientation(self):
        """A 180-degree coupon is resolved by the identity ring, not by the invert prior."""
        truth = dict(TRUTH, rot_deg=185.0)
        res, _ = solve_galvo_coupon(render_coupon(**truth), PARAMS)
        self.assertEqual(res['orientation']['source'], 'identity')
        self.assertFalse(res['orientation']['matches_invert'])
        self.assertAlmostEqual(res['scale_x'], 1.02, delta=0.00102)
        self.assertAlmostEqual(res['scale_y'], 0.98, delta=0.00098)
        self.assertAlmostEqual(res['skew_deg'], 0.3, delta=0.02)
        self.assertAlmostEqual(res['rotation_deg'], -175.0, delta=0.05)

    def test_mirrored_coupon_is_flagged(self):
        res, _ = solve_galvo_coupon(render_coupon(scale_x=-1.02, scale_y=0.98, skew_deg=0.3, rot_deg=5.0), PARAMS)
        self.assertTrue(res['mirrored'])
        self.assertAlmostEqual(res['scale_x'], 1.02, delta=0.00102)
        self.assertAlmostEqual(res['scale_y'], 0.98, delta=0.00098)

    def test_ruler_invalid_with_four_vertices(self):
        img = render_coupon(drop_l=(0, 1, 2, 3), **TRUTH)
        with self.assertRaises(SolveError) as ctx:
            solve_galvo_coupon(img, PARAMS)
        self.assertEqual(ctx.exception.info, 'RULER_INVALID')
        self.assertIn('only 4 L vertices', ctx.exception.reason)

    def test_six_vertices_is_enough(self):
        res, _ = solve_galvo_coupon(render_coupon(drop_l=(0, 7), **TRUTH), PARAMS)
        self.assertEqual(res['ruler']['vertices_used'], 6)
        self.assertAlmostEqual(res['scale_x'], 1.02, delta=0.00102)

    def test_broken_corners_are_paired(self):
        """An L whose corner did not cut is two arms; their lines still meet at the vertex."""
        img = render_coupon(**TRUTH)
        for vx, vy in l_frame_vertices():
            cv2.circle(img, (int(1800 + vx * 20), int(1800 + vy * 20)), 14, (30, 30, 30), -1)
        res, _ = solve_galvo_coupon(img, PARAMS)
        assert_truth(self, res)

    def test_low_contrast_frame_under_uneven_light_uses_tophat(self):
        """Camera case: the L grooves sit 60 above a background that drifts by 120 across the image."""
        full = render_coupon(**TRUTH)
        no_frame = render_coupon(drop_l=tuple(range(8)), **TRUTH)
        is_frame = np.any(full != no_frame, axis=2)
        ramp = np.linspace(0, 120, full.shape[1], dtype=np.float32)[None, :, None]
        img = np.clip(no_frame.astype(np.float32) + ramp, 0, 255)
        img[is_frame] = np.clip(30 + ramp[0, :, 0][np.nonzero(is_frame)[1]][:, None] + 60, 0, 255)
        img = img.astype(np.uint8)
        res, _ = solve_galvo_coupon(img, dict(PARAMS, guided=False))
        assert_truth(self, res)
        self.assertEqual(res['ruler']['threshold'][2], 2.0)
        # and the guided detection, which does not threshold, is not troubled by the light
        res, _ = solve_galvo_coupon(img, PARAMS)
        assert_truth(self, res)
        self.assertEqual(res['ruler']['threshold'][0], 'guided')

    def test_dark_slit_frame_is_found_too(self):
        """Camera case: a cut-through L photographs as a dark line; the masks want bright ones."""
        full = render_coupon(**TRUTH)
        no_frame = render_coupon(drop_l=tuple(range(8)), **TRUTH)
        img = no_frame.copy()
        img[np.any(full != no_frame, axis=2)] = (5, 5, 5)
        res, _ = solve_galvo_coupon(img, PARAMS)
        assert_truth(self, res)
        self.assertEqual(res['ruler']['threshold'][0], 'guided')

    def test_hand_held_photograph_needs_the_projective_ruler(self):
        """A phone photograph of the flat sheet is a homography of it, which no affine ruler fits."""
        img = render_coupon(**TRUTH)
        src = np.float32([[0, 0], [3600, 0], [3600, 3600], [0, 3600]])
        dst = np.float32([[120, 60], [3480, 0], [3600, 3600], [0, 3540]])
        warped = cv2.warpPerspective(img, cv2.getPerspectiveTransform(src, dst), (3600, 3600))
        with self.assertRaises(SolveError) as ctx:
            solve_galvo_coupon(warped, PARAMS)
        self.assertEqual(ctx.exception.info, 'RULER_INVALID')
        res, _ = solve_galvo_coupon(warped, dict(PARAMS, ruler_model='auto'))
        assert_truth(self, res)
        self.assertEqual(res['ruler']['model'], 'projective')

    def test_locate_finds_the_coupon_at_an_unknown_scale(self):
        """A photograph of unknown scale: the centre and px/mm given are only a starting point."""
        img = render_coupon(px_per_mm=15.0, center_px=(1500, 2000), **TRUTH)
        params = dict(PARAMS, px_per_mm=20, expected_center_px=[1800, 1800], locate=True)
        res, _ = solve_galvo_coupon(img, params)
        assert_truth(self, res)
        self.assertAlmostEqual(res['located']['px_per_mm'], 15.0, delta=0.75)
        np.testing.assert_allclose(
            res['located']['center_px'], [1500, 2000], atol=6 * 15
        )  # the galvo marks sit offset_mm off the frame centre
        self.assertAlmostEqual(res['ruler']['px_per_mm_x'], 15.0, delta=0.02)

    def test_rotate_auto_turns_a_sideways_scan_the_right_way_up(self):
        """A sheet scanned on its side: the identity ring says which way is up."""
        img = cv2.rotate(render_coupon(**TRUTH), cv2.ROTATE_90_CLOCKWISE)
        # as it is, the frame's own rotation absorbs the quarter turn and the galvo axes come out
        # 90 degrees off; turned the right way up, the numbers are the sheet's
        sideways, _ = solve_galvo_coupon(img, PARAMS)
        self.assertGreater(abs(sideways['rotation_deg']), 45)
        res, annotated = solve_galvo_coupon(img, dict(PARAMS, rotate='auto', annotate=True))
        assert_truth(self, res)
        self.assertEqual(res['rotated_deg'], 270)
        self.assertEqual(res['orientation']['source'], 'identity')
        self.assertEqual(annotated.shape, (3600, 3600, 3))

    def test_ruler_invalid_without_frame(self):
        img = render_coupon(drop_l=tuple(range(8)), **TRUTH)
        with self.assertRaises(SolveError) as ctx:
            solve_galvo_coupon(img, PARAMS)
        self.assertEqual(ctx.exception.info, 'RULER_INVALID')


if __name__ == '__main__':
    unittest.main()
