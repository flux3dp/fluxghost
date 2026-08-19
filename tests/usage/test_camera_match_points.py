"""Unit tests for the solve_pnp corner matcher (fluxghost/utils/camera/corner_detection/match_points.py).

No server needed; the matcher is pure numpy/scipy. It is exercised by
`solve_pnp_find_corners` (docs/api/camera-calibration.md).
"""

import unittest

import numpy as np

from fluxghost.utils.camera.corner_detection.match_points import match_projected_points

# A 2x2 reference pattern as rvec/tvec would project it
PROJECTED = np.array([[1000.0, 1000.0], [1400.0, 1000.0], [1000.0, 1400.0], [1400.0, 1400.0]])


class MatchProjectedPointsTest(unittest.TestCase):
    def test_exact_match(self):
        match = match_projected_points(PROJECTED.copy(), PROJECTED)
        self.assertIsNotNone(match)
        np.testing.assert_allclose(match.points, PROJECTED)
        self.assertAlmostEqual(match.abs_score, 1.0)

    def test_translated_pattern_still_matches(self):
        """The pose prior must not veto a pattern that clearly matches (relative-only gate)."""
        shifted = PROJECTED + np.array([900.0, 700.0])
        match = match_projected_points(shifted, PROJECTED)
        self.assertIsNotNone(match)
        np.testing.assert_allclose(match.points, shifted)
        self.assertLess(match.abs_score, 0.01)

    def test_absolute_term_breaks_the_tie(self):
        """Two identical patterns: the one near the projected pose wins."""
        near = PROJECTED + np.array([40.0, 0.0])
        far = PROJECTED + np.array([1500.0, 900.0])
        match = match_projected_points(np.concatenate([far, near]), PROJECTED)
        self.assertIsNotNone(match)
        np.testing.assert_allclose(match.points, near)

    def test_no_match(self):
        noise = np.array([[10.0, 10.0], [3000.0, 20.0], [50.0, 2500.0], [3500.0, 2600.0]])
        self.assertIsNone(match_projected_points(noise, PROJECTED))

    def test_too_few_corners(self):
        self.assertIsNone(match_projected_points(PROJECTED[:3], PROJECTED))

    def test_wobbly_point_is_kept(self):
        """Pins the REL_SIGMA=60 / min_point_score=0.1 tolerance: 80 px off still counts as a match."""
        corners = PROJECTED + np.array([[0.0, 0.0], [0.0, 0.0], [0.0, 0.0], [80.0, 0.0]])
        match = match_projected_points(corners, PROJECTED)
        self.assertIsNotNone(match)
        self.assertGreater(match.score_detail[3], 0.1)
        np.testing.assert_allclose(match.points, corners)

    def test_missing_corner_falls_back_to_projected_offset(self):
        """A point with no corner near it is rebuilt from the anchor plus its projected offset."""
        corners = np.concatenate([PROJECTED[:3], np.array([[2500.0, 2500.0]])])
        match = match_projected_points(corners, PROJECTED)
        self.assertIsNotNone(match)
        np.testing.assert_allclose(match.points, PROJECTED)


if __name__ == '__main__':
    unittest.main()
