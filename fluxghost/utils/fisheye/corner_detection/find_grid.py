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
    origin_k=25,
):
    corner_tree = spatial.KDTree(corners)

    def findPoint(point,used_points=None, k=3):
        x, y = point
        dists, indices = corner_tree.query([x, y], k=k)
        for i in range(k):
            index = indices[i]
            point = int(corners[index][0]), int(corners[index][1])
            if used_points is not None and point in used_points:
                continue
            dist = dists[i]
            return point, dist
        point = corners[indices[0]]
        return (int(point[0]), int(point[1])), dists[0]

    grids = []
    for j in y_grid:
        grids.append([])
        for i in x_grid:
            grids[-1].append((i, j))

    x0, y0 = get_origin(height, remapped, with_pitch=with_pitch)
    _, indices = corner_tree.query([x0, y0], k=origin_k)
    res = None
    for index in indices:
        current_point = int(corners[index][0]), int(corners[index][1])
        total_err = 0
        # Create a 2d map of the grid to store the corner points
        grid_points = [[None for _ in range(len(x_grid))] for _ in range(len(y_grid))]
        derised_points = [[None for _ in range(len(x_grid))] for _ in range(len(y_grid))]
        derised_points[0][0] = (x0, y0)
        large_dist_points = set()
        large_dist_threshold = 20
        grid_points[0][0] = current_point
        used_points = set()
        used_points.add(tuple(current_point))
        has_duplicate_points = False

        for j in range(len(y_grid)):
            for i in range(len(x_grid)):
                xr, yr, yxr, xyr = get_pixel_ratio(height, x_grid[i], y_grid[j], remapped, with_pitch)
                if i == 0:
                    if j == 0:
                        continue
                    elif grid_points[j - 1][i] is not None:
                        dist = grids[j][i][1] - grids[j - 1][i][1]
                        desire_point = grid_points[j - 1][i][0] + dist * yxr, grid_points[j - 1][i][1] + dist * yr
                        new_point, d = findPoint(desire_point, used_points)
                        if d > large_dist_threshold:
                            large_dist_points.add((i, j))
                        total_err += d
                elif grid_points[j][i - 1] is not None:
                    dist = grids[j][i][0] - grids[j][i - 1][0]
                    desire_point = grid_points[j][i - 1][0] + dist * xr, grid_points[j][i - 1][1] + dist * xyr
                    new_point, d = findPoint(desire_point, used_points)
                    if d > large_dist_threshold:
                        large_dist_points.add((i, j))
                    total_err += d
                grid_points[j][i] = new_point
                derised_points[j][i] = desire_point
                if new_point in used_points:
                    has_duplicate_points = True
                used_points.add(new_point)
                current_point = new_point
        if res is None or total_err < res[1]:
            logger.info('point (%s, %s) total error: %s' % (grid_points[0][0][0], grid_points[0][0][1], total_err))
            res = (grid_points, has_duplicate_points, large_dist_points, derised_points), total_err
    grid_points, has_duplicate_points, large_dist_points, derised_points = res[0]
    if draw:
        for j in range(len(y_grid)):
            for i in range(len(x_grid)):
                is_large_dist_point = (i, j) in large_dist_points
                red = (0, 0, 255)
                green = (0, 255, 0)
                color = red if is_large_dist_point else green
                if i > 0:
                    cv2.line(img, grid_points[j][i], grid_points[j][i - 1], color, 1)
                if j > 0:
                    cv2.line(img, grid_points[j][i], grid_points[j - 1][i], color, 1)
                cv2.circle(img, grid_points[j][i], 10, color, 1)
                cv2.circle(img, grid_points[j][i], 0, color, 1)
                desire_point = tuple(map(int, derised_points[j][i]))
                cv2.circle(img, desire_point, 0, color, 1)
                cv2.rectangle(
                    img,
                    (desire_point[0] - 3, desire_point[1] - 3),
                    (desire_point[0] + 3, desire_point[1] + 3),
                    color,
                    1,
                )
    if has_duplicate_points:
        logger.warning('Duplicate points found')
    return grid_points, has_duplicate_points
