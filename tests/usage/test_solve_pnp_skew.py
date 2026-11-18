"""solve_pnp must invert project_points for a fisheye k with a skew term.

Parameters calibrated before CALIB_FIX_SKEW was added can carry one (a unit in the field had k[0][1] = -7.1).
The old solve re-projected with P=k and solved with k, which is not a round trip under skew: the pose came out
about 0.2 mm off and the preview, which projects through project_points, inherited it.
"""

import unittest

import cv2
import numpy as np

from fluxghost.utils.camera.calibration import CALIBRATION_FLAGS_FISHEYE, project_points
from fluxghost.utils.camera.solve_pnp import solve_pnp

D = np.array([[0.0], [0.2418], [-0.1341], [-0.0008]])
RVEC = np.array([[0.38], [0.0], [-0.02]])
TVEC = np.array([[-213.0], [-83.0], [123.0]])
OBJ = np.array([[30, 30, 0], [330, 30, 0], [30, 210, 0], [330, 210, 0], [180, 120, 0]], float).reshape(-1, 1, 3)


def k_with(skew):
    return np.array([[1357.3, skew, 2799.4], [0, 1382.4, 2075.9], [0, 0, 1.0]])


class TestSolvePnpSkew(unittest.TestCase):
    def test_round_trip(self):
        for skew in (0.0, -7.13):
            with self.subTest(skew=skew):
                k = k_with(skew)
                img = project_points(OBJ, RVEC, TVEC, k, D, is_fisheye=True)
                ok, rvec, tvec = solve_pnp(OBJ, img, k, D, is_fisheye=True)
                self.assertTrue(ok)
                np.testing.assert_allclose(rvec, RVEC, atol=1e-5)
                np.testing.assert_allclose(tvec, TVEC, atol=1e-3)

    def test_calibration_fixes_skew(self):
        self.assertTrue(CALIBRATION_FLAGS_FISHEYE & cv2.fisheye.CALIB_FIX_SKEW)


if __name__ == '__main__':
    unittest.main()
