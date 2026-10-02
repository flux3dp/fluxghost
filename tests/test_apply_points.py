"""Map-based apply_points must match the old per-cell warpPerspective output."""

import unittest

import cv2
import numpy as np

from fluxghost.utils.camera.corner_detection.apply_points import apply_points


def apply_points_reference(img, corners, x_grid, y_grid, padding, perspective_pixel_per_mm):
    img_h = y_grid[-1] * perspective_pixel_per_mm + padding * 2
    img_w = x_grid[-1] * perspective_pixel_per_mm + padding * 2
    base_img = np.zeros((img_h, img_w, 3), np.uint8)
    for y in range(len(y_grid) - 1):
        for x in range(len(x_grid) - 1):
            left, r, t, b = x_grid[x], x_grid[x + 1], y_grid[y], y_grid[y + 1]
            dst_w = (r - left) * perspective_pixel_per_mm
            dst_h = (b - t) * perspective_pixel_per_mm
            dst_l = padding if x == 0 else 0
            dst_t = padding if y == 0 else 0
            dst_points = np.float32(
                [[dst_l, dst_t], [dst_l + dst_w, dst_t], [dst_l, dst_t + dst_h], [dst_l + dst_w, dst_t + dst_h]]
            )
            src_points = np.float32([corners[y][x], corners[y][x + 1], corners[y + 1][x], corners[y + 1][x + 1]])
            m = cv2.getPerspectiveTransform(src_points, dst_points)
            draw_w, draw_h = dst_w, dst_h
            if x == 0 or x == len(x_grid) - 2:
                draw_w += padding if len(x_grid) > 1 else padding * 2
            if y == 0 or y == len(y_grid) - 2:
                draw_h += padding if len(y_grid) > 1 else padding * 2
            out = cv2.warpPerspective(img, m, (draw_w, draw_h))
            img_l = 0 if left == 0 else left * perspective_pixel_per_mm + padding
            img_t = 0 if t == 0 else t * perspective_pixel_per_mm + padding
            base_img[img_t : img_t + draw_h, img_l : img_l + draw_w] = out
    return base_img


class ApplyPointsTest(unittest.TestCase):
    def check(self, x_grid, y_grid, padding):
        rng = np.random.RandomState(0)
        img = rng.randint(0, 255, (600, 800, 3), np.uint8)
        # mildly warped grid inside the image
        xs = 100 + np.asarray(x_grid, np.float32) * 1.4
        ys = 80 + np.asarray(y_grid, np.float32) * 1.3
        corners = np.stack(np.meshgrid(xs, ys), axis=-1) + rng.uniform(-2, 2, (len(y_grid), len(x_grid), 2))
        corners = corners.astype(np.float32)
        want = apply_points_reference(img, corners, x_grid, y_grid, padding, 2)
        got = apply_points(img, corners, x_grid, y_grid, padding=padding, perspective_pixel_per_mm=2)
        self.assertEqual(got.shape, want.shape)
        diff = np.abs(got.astype(int) - want.astype(int))
        # fixed-point maps vs warpPerspective differ by rounding only
        self.assertLess(diff.mean(), 1.0)
        self.assertGreater((diff <= 8).mean(), 0.99)

    def test_grid_with_padding(self):
        self.check(list(range(0, 401, 10)), list(range(0, 301, 10)), padding=150)

    def test_grid_without_padding(self):
        self.check(list(range(0, 201, 20)), list(range(0, 161, 20)), padding=0)

    def test_single_cell(self):
        self.check([0, 100], [0, 80], padding=20)


if __name__ == '__main__':
    unittest.main()
