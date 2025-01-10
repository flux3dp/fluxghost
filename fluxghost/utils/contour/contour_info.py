import math

import cv2
import numpy as np
from scipy.spatial import cKDTree


def get_center(contour):
    moment = cv2.moments(contour)
    if moment["m00"] == 0:
        cx, cy = 0, 0
    else:
        cx = int(moment["m10"] / moment["m00"])
        cy = int(moment["m01"] / moment["m00"])
    return cx, cy


def get_rotation_kd_tree(contour):
    center = get_center(contour)
    points = contour.reshape(-1, 2) - center
    kd_tree = cKDTree(points)
    return kd_tree


def find_rotation_angle(contour, kd_tree, angle_step=0.5):
    res = float('inf'), 0
    points = contour.reshape(-1, 2)

    for angle in np.arange(0, 360, angle_step):
        rad = math.radians(angle)
        c, s = math.cos(-rad), math.sin(-rad)
        R = np.array([[c, -s], [s, c]])
        rotated = np.dot(points, R.T)
        distances, _ = kd_tree.query(rotated)
        err = np.sum(distances)
        if err < res[0]:
            res = err, angle
    return res[1]


def get_contour_info(contour, base_contour_kd_tree, include_contour=False):
    center = get_center(contour)
    if base_contour_kd_tree:
        angle = find_rotation_angle(contour.reshape(-1, 2) - center, base_contour_kd_tree)
        angle = math.radians(angle)
    else:
        angle = 0
    bbox = cv2.boundingRect(contour)
    res = {'center': center, 'angle': angle, 'bbox': bbox}
    if include_contour:
        res['contour'] = contour.reshape(-1, 2).tolist()
    return res
