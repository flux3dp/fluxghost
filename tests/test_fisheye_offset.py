"""Manual bed-plane offset: object points shift before projection, grid axes stay put."""

import unittest

import numpy as np

from fluxghost.utils.camera.calibration import project_points
from fluxghost.utils.camera.perspective import (
    calculate_regional_perspective_points,
    generate_grid_objects,
    region_offset_sampler,
)

# Pinhole-like fisheye camera 300 mm above the bed, looking straight down, no distortion.
K = np.array([[1000.0, 0.0, 640.0], [0.0, 1000.0, 480.0], [0.0, 0.0, 1.0]])
D = np.zeros((4, 1))
RVEC = np.zeros((3, 1))
TVEC = np.array([[0.0], [0.0], [300.0]])
REGIONS = ['topLeft', 'top', 'topRight', 'left', 'center', 'right', 'bottomLeft', 'bottom', 'bottomRight']


def regional(step=10, **kwargs):
    rvecs = {r: RVEC for r in REGIONS}
    tvecs = {r: TVEC for r in REGIONS}
    points, xgrid, ygrid = calculate_regional_perspective_points(
        [0, 30, step], [0, 30, step], 0, K, D, rvecs, tvecs, total_width=30, total_height=30, **kwargs
    )
    return points, xgrid, ygrid


def expected_shift_px(dx_mm, dy_mm):
    """Pixel displacement of a (dx, dy) mm step on the bed for this camera."""
    a = project_points(np.array([[[0.0, 0.0, 0.0]]], np.float32), RVEC, TVEC, K, D)[0][0]
    b = project_points(np.array([[[dx_mm, dy_mm, 0.0]]], np.float32), RVEC, TVEC, K, D)[0][0]
    return b - a


class FisheyeOffsetTest(unittest.TestCase):
    def test_global_offset_shifts_every_point_and_keeps_grid(self):
        base, xg, yg = regional()
        shifted, xg2, yg2 = regional(offset=(1, 0))
        np.testing.assert_array_equal(xg, xg2)
        np.testing.assert_array_equal(yg, yg2)
        np.testing.assert_allclose(shifted - base, np.broadcast_to(expected_shift_px(1, 0), base.shape), atol=1e-2)

    def test_region_offsets_apply_only_to_their_region(self):
        base, _, _ = regional()
        shifted, _, _ = regional(offset=(0, 0), region_offsets={'topLeft': (1, 0), 'blend': False})
        delta = shifted - base
        # region is chosen from the unshifted point: x, y in [0, 10) -> topLeft (grid rows 0, cols 0)
        np.testing.assert_allclose(delta[0][0], expected_shift_px(1, 0), atol=1e-2)
        np.testing.assert_allclose(delta[0][1:], 0, atol=1e-6)
        np.testing.assert_allclose(delta[1:], 0, atol=1e-6)

    def test_region_offsets_fall_back_to_global_offset(self):
        base, _, _ = regional()
        shifted, _, _ = regional(offset=(0, 2), region_offsets={'center': (0, 0), 'blend': False})
        delta = shifted - base
        # center region = x, y in [10, 20) -> grid index [1][1]
        np.testing.assert_allclose(delta[1][1], 0, atol=1e-6)
        np.testing.assert_allclose(delta[0][0], expected_shift_px(0, 2), atol=1e-2)

    def test_sampler_plateau_and_band(self):
        # topLeft = 1, rest 0; along the top row: exact over the middle two thirds, linear across the
        # 1/3-wide band at the border, nothing at the far edge
        table = [[(1, 0), (0, 0), (0, 0)], [(0, 0)] * 3, [(0, 0)] * 3]
        f = region_offset_sampler(table)
        for tx, ox in [(0.0, 1), (0.8, 1), (1.0, 0.5), (1 + 1 / 12, 0.25), (1.5, 0), (2.9, 0)]:
            np.testing.assert_allclose(f((0, tx)), (ox, 0), err_msg=f'tx={tx}')
        np.testing.assert_allclose(f((1.0, 1.0)), (0.25, 0))  # corner of four regions

    def test_blend_ramps_region_offset_into_neighbours(self):
        # grid points every 1 mm; region width 10, so x = 8 is the plateau edge and x = 10 the border
        base, _, _ = regional(step=1)
        shifted, _, _ = regional(step=1, offset=(0, 0), region_offsets={'topLeft': (1, 0)})
        delta = shifted - base
        np.testing.assert_allclose(delta[0][0], expected_shift_px(1, 0), atol=1e-2)
        np.testing.assert_allclose(delta[0][8], expected_shift_px(1, 0), atol=1e-2)
        np.testing.assert_allclose(delta[0][10], expected_shift_px(0.5, 0), atol=1e-2)
        np.testing.assert_allclose(delta[10][0], expected_shift_px(0.5, 0), atol=1e-2)
        np.testing.assert_allclose(delta[10][10], expected_shift_px(0.25, 0), atol=1e-2)
        np.testing.assert_allclose(delta[0][12], 0, atol=1e-6)
        np.testing.assert_allclose(delta[15], 0, atol=1e-6)

    def test_blend_is_identity_on_a_uniform_table(self):
        step, _, _ = regional(step=1, region_offsets={**{r: (1, -0.5) for r in REGIONS}, 'blend': False})
        blended, _, _ = regional(step=1, region_offsets={r: (1, -0.5) for r in REGIONS})
        np.testing.assert_allclose(blended, step, atol=1e-6)

    def test_v3_grid_shift_matches_projection(self):
        # mirrors set_fisheye_grid: objp + offset, then project
        _, _, objp = generate_grid_objects([0, 10, 10], [0, 10, 10])
        base = project_points(objp.reshape(-1, 1, 3).astype(np.float32), RVEC, TVEC, K, D)
        moved = project_points((objp + np.array([1, 0, 0])).reshape(-1, 1, 3).astype(np.float32), RVEC, TVEC, K, D)
        np.testing.assert_allclose(moved - base, np.broadcast_to(expected_shift_px(1, 0), base.shape), atol=1e-2)


if __name__ == '__main__':
    unittest.main()
