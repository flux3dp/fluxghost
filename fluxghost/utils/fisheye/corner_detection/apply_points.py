import cv2
import numpy as np

from ..constants import DPMM


def apply_points(img, corners, x_grid, y_grid, padding=100, perspective_pixel_per_mm=DPMM):
    img_h = y_grid[-1] * perspective_pixel_per_mm + padding * 2
    img_w = x_grid[-1] * perspective_pixel_per_mm + padding * 2
    base_img = np.zeros((img_h, img_w, 3), np.uint8)

    for y in range(len(y_grid) - 1):
        for x in range(len(x_grid) - 1):
            left = x_grid[x]
            r = x_grid[x + 1]
            t = y_grid[y]
            b = y_grid[y + 1]

            dst_w = (r - left) * perspective_pixel_per_mm
            dst_h = (b - t) * perspective_pixel_per_mm
            dst_l = padding if x == 0 else 0
            dst_t = padding if y == 0 else 0
            dst_points = np.float32(
                [
                    [dst_l, dst_t],
                    [dst_l + dst_w, dst_t],
                    [dst_l, dst_t + dst_h],
                    [dst_l + dst_w, dst_t + dst_h],
                ]
            )
            lt = corners[y][x]
            rt = corners[y][x + 1]
            lb = corners[y + 1][x]
            rb = corners[y + 1][x + 1]
            src_points = np.float32([lt, rt, lb, rb])

            perspective_matrix = cv2.getPerspectiveTransform(src_points, dst_points)

            # draw the perspective transformation to the input image, padding img at edges
            draw_w, draw_h = dst_w, dst_h
            if x == 0 or x == len(x_grid) - 2:
                draw_w += padding if len(x_grid) > 1 else padding * 2
            if y == 0 or y == len(y_grid) - 2:
                draw_h += padding if len(y_grid) > 1 else padding * 2
            out = cv2.warpPerspective(img, perspective_matrix, (draw_w, draw_h))

            img_l = 0 if left == 0 else left * perspective_pixel_per_mm + padding
            img_t = 0 if t == 0 else t * perspective_pixel_per_mm + padding
            base_img[img_t : img_t + draw_h, img_l : img_l + draw_w] = out
    return base_img
