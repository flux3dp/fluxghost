import logging
from typing import List

import cv2
import scipy.spatial as spatial

from .estimation import get_origin, get_pixel_ratio

logger = logging.getLogger('utils.fisheye.corner_detection.find_grid')

def find_grid(
    img,
    corners,
    height,
    x_grid: List[int],
    y_grid: List[int],
    remapped=False,
    with_pitch=False,
    draw=False,
):
    corner_tree = spatial.KDTree(corners)

    def findPoint(x, y):
        dist, index = corner_tree.query([x, y], k=1)
        point = corners[index]
        return (int(point[0]), int(point[1])), dist

    grids = []
    for j in y_grid:
        grids.append([])
        for i in x_grid:
            grids[-1].append((i, j))

    x0, y0 = get_origin(height, remapped, with_pitch=with_pitch)
    _, indices = corner_tree.query([x0, y0], k=25)
    res = None
    for index in indices:
        current_point = int(corners[index][0]), int(corners[index][1])
        total_err = 0
        # Create a 2d map of the grid to store the corner points
        grid_map = [[None for _ in range(len(x_grid))] for _ in range(len(y_grid))]
        large_dist_points = set()
        large_dist_threshold = 20
        grid_map[0][0] = current_point
        used_points = set()
        used_points.add(tuple(current_point))
        has_duplicate_points = False

        for j in range(len(y_grid)):
            for i in range(len(x_grid)):
                xr, yr, yxr, xyr = get_pixel_ratio(height, x_grid[i], y_grid[j], remapped, with_pitch)
                if i == 0:
                    if j == 0:
                        continue
                    elif grid_map[j - 1][i] is not None:
                        dist = grids[j][i][1] - grids[j - 1][i][1]
                        desire_point = int(grid_map[j - 1][i][0] + dist * yxr), int(grid_map[j - 1][i][1] + dist * yr)
                        new_point, d = findPoint(
                            desire_point[0],
                            desire_point[1],
                        )
                        if d > large_dist_threshold:
                            large_dist_points.add((i, j))
                        total_err += d
                elif grid_map[j][i - 1] is not None:
                    dist = grids[j][i][0] - grids[j][i - 1][0]
                    desire_point = int(grid_map[j][i - 1][0] + dist * xr), int(grid_map[j][i - 1][1] + dist * xyr)
                    new_point, d = findPoint(
                        desire_point[0],
                        desire_point[1],
                    )
                    if d > large_dist_threshold:
                        large_dist_points.add((i, j))
                    total_err += d
                grid_map[j][i] = new_point
                if tuple(new_point) in used_points:
                    has_duplicate_points = True

                used_points.add(tuple(new_point))
                current_point = new_point
        if res is None or total_err < res[1]:
            logger.info('point (%s, %s) total error: %s' % (grid_map[0][0][0], grid_map[0][0][1], total_err))
            print(total_err, grid_map[0][0])
            res = (grid_map, has_duplicate_points, large_dist_points), total_err
    grid_map, has_duplicate_points, large_dist_points = res[0]
    if draw:
        for j in range(len(y_grid)):
            for i in range(len(x_grid)):
                is_large_dist_point = (i, j) in large_dist_points
                red = (0, 0, 255)
                green = (0, 255, 0)
                color = red if is_large_dist_point else green
                if i > 0:
                    cv2.line(img, grid_map[j][i], grid_map[j][i - 1], color, 1)
                if j > 0:
                    cv2.line(img, grid_map[j][i], grid_map[j - 1][i], color, 1)
                cv2.circle(img, grid_map[j][i], 10, color, 1)
                cv2.circle(img, grid_map[j][i], 0, color, 1)
    if has_duplicate_points:
        logger.warning('Duplicate points found')
    return grid_map, has_duplicate_points
