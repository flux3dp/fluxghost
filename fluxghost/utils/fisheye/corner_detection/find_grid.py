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
        _, index = corner_tree.query([x, y])
        point = corners[index]
        return (int(point[0]), int(point[1]))

    grids = []
    for j in y_grid:
        grids.append([])
        for i in x_grid:
            grids[-1].append((i, j))
    # Create a 2d map of the grid to store the corner points
    grid_map = [[None for _ in range(len(x_grid))] for _ in range(len(y_grid))]

    x0, y0 = get_origin(height, remapped, with_pitch=with_pitch)
    current_point = findPoint(x0, y0)
    grid_map[0][0] = current_point
    used_points = set()
    used_points.add(tuple(current_point))
    has_duplicate_points = False

    for j in range(len(y_grid)):
        for i in range(len(x_grid)):
            xr, yr, yxr, xyr = get_pixel_ratio(height, x_grid[i], y_grid[j], remapped, with_pitch)
            if i == 0:
                if j == 0:
                    if draw:
                        cv2.circle(img, current_point, 10, (0, 0, 255), 1)
                        cv2.circle(img, current_point, 0, (0, 0, 255), 1)
                    continue
                elif grid_map[j - 1][i] is not None:
                    dist = grids[j][i][1] - grids[j - 1][i][1]
                    desire_point = int(grid_map[j - 1][i][0] + dist * yxr), int(grid_map[j - 1][i][1] + dist * yr)
                    if draw:
                        cv2.rectangle(
                            img,
                            (desire_point[0] - 5, desire_point[1] - 5),
                            (desire_point[0] + 5, desire_point[1] + 5),
                            (0, 0, 255),
                            1,
                        )
                    new_point = findPoint(
                        desire_point[0],
                        desire_point[1],
                    )
            elif grid_map[j][i - 1] is not None:
                dist = grids[j][i][0] - grids[j][i - 1][0]
                desire_point = int(grid_map[j][i - 1][0] + dist * xr), int(grid_map[j][i - 1][1] + dist * xyr)
                new_point = findPoint(
                    desire_point[0],
                    desire_point[1],
                )
                if draw:
                    cv2.rectangle(
                        img,
                        (desire_point[0] - 5, desire_point[1] - 5),
                        (desire_point[0] + 5, desire_point[1] + 5),
                        (0, 0, 255),
                        1,
                    )
            grid_map[j][i] = new_point
            if tuple(new_point) in used_points:
                has_duplicate_points = True

            used_points.add(tuple(new_point))
            if draw:
                if i > 0:
                    cv2.line(img, new_point, grid_map[j][i - 1], (0, 0, 255), 1)
                if j > 0:
                    cv2.line(img, new_point, grid_map[j - 1][i], (0, 0, 255), 1)
                cv2.circle(img, new_point, 10, (0, 0, 255), 1)
                cv2.circle(img, new_point, 0, (0, 0, 255), 1)
            current_point = new_point
    if has_duplicate_points:
        logger.warning('Duplicate points found')
    return grid_map, has_duplicate_points
