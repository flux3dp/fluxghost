import logging
from time import perf_counter

import cv2
import numpy as np

from ..constants import DPMM

logger = logging.getLogger('utils.camera.apply_points')

# ponytail: single-entry cache — one camera at a time; keyed dict if that changes
_grid_map_cache = {}


def build_grid_map(corners, x_grid, y_grid, padding=100, perspective_pixel_per_mm=DPMM):
    """Build one dst->src lookup map covering every grid cell, so the per-cell
    warpPerspective loop collapses into a single cv2.remap."""
    img_h = y_grid[-1] * perspective_pixel_per_mm + padding * 2
    img_w = x_grid[-1] * perspective_pixel_per_mm + padding * 2
    # -1 = outside the source, so uncovered pixels stay black like the old per-cell draw
    map_x = np.full((img_h, img_w), -1, np.float32)
    map_y = np.full((img_h, img_w), -1, np.float32)

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

            # dst -> src (what warpPerspective computes internally via the inverse matrix)
            inverse_matrix = cv2.getPerspectiveTransform(dst_points, src_points)

            # edge cells extend into the padding, same as the old per-cell draw size
            draw_w, draw_h = dst_w, dst_h
            if x == 0 or x == len(x_grid) - 2:
                draw_w += padding if len(x_grid) > 1 else padding * 2
            if y == 0 or y == len(y_grid) - 2:
                draw_h += padding if len(y_grid) > 1 else padding * 2

            us, vs = np.meshgrid(np.arange(draw_w, dtype=np.float32), np.arange(draw_h, dtype=np.float32))
            local = np.stack([us, vs], axis=-1).reshape(-1, 1, 2)
            src = cv2.perspectiveTransform(local, inverse_matrix).reshape(draw_h, draw_w, 2)

            img_l = 0 if left == 0 else left * perspective_pixel_per_mm + padding
            img_t = 0 if t == 0 else t * perspective_pixel_per_mm + padding
            map_x[img_t : img_t + draw_h, img_l : img_l + draw_w] = src[..., 0]
            map_y[img_t : img_t + draw_h, img_l : img_l + draw_w] = src[..., 1]

    # fixed-point maps: faster remap, less memory than two float32 planes
    return cv2.convertMaps(map_x, map_y, cv2.CV_16SC2)


def apply_points(img, corners, x_grid, y_grid, padding=100, perspective_pixel_per_mm=DPMM):
    key = (
        np.asarray(corners).tobytes(),
        np.asarray(x_grid).tobytes(),
        np.asarray(y_grid).tobytes(),
        padding,
        perspective_pixel_per_mm,
    )
    maps = _grid_map_cache.get(key)
    if maps is None:
        t0 = perf_counter()
        maps = build_grid_map(corners, x_grid, y_grid, padding, perspective_pixel_per_mm)
        _grid_map_cache.clear()
        _grid_map_cache[key] = maps
        logger.info('[timing] grid map built in %.1f ms (%dx%d)', (perf_counter() - t0) * 1000, *maps[0].shape[1::-1])
    return cv2.remap(img, maps[0], maps[1], cv2.INTER_LINEAR)
