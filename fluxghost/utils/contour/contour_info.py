import math

import cv2
import numpy as np
from scipy.spatial import cKDTree

from .contour_data import ContourData


def get_center(contour):
    moment = cv2.moments(contour)
    if moment['m00'] == 0:
        cx, cy = 0, 0
    else:
        cx = int(moment['m10'] / moment['m00'])
        cy = int(moment['m01'] / moment['m00'])
    return cx, cy


def get_rotation_kd_tree(contour):
    center = get_center(contour)
    points = contour.reshape(-1, 2) - center
    kd_tree = cKDTree(points)
    return kd_tree


def find_rotation_angle(contour, kd_tree, angle_step=0.5):
    points = contour.reshape(-1, 2)
    angles = np.arange(0, 360, angle_step)
    errors = np.empty(len(angles))

    for idx, angle in enumerate(angles):
        rad = math.radians(angle)
        c, s = math.cos(-rad), math.sin(-rad)
        R = np.array([[c, -s], [s, c]])
        rotated = np.dot(points, R.T)
        distances, _ = kd_tree.query(rotated)
        errors[idx] = np.sum(distances)

    mean_err = np.mean(errors)
    std_err = np.std(errors)
    threshold = mean_err - std_err
    candidate_mask = errors < threshold

    # Group consecutive candidates and pick the min-error one per group
    groups = []
    i = 0
    n = len(angles)
    while i < n:
        if candidate_mask[i]:
            group = []
            while i < n and candidate_mask[i]:
                group.append(i)
                i += 1
            groups.append(group)
        else:
            i += 1

    # Handle wrap-around: merge first and last group if both touch the boundary
    if len(groups) > 1 and groups[0][0] == 0 and groups[-1][-1] == n - 1:
        groups[0] = groups[-1] + groups[0]
        groups.pop()

    # From each group, pick the index with minimum error
    candidates = []
    for group in groups:
        best_idx = min(group, key=lambda idx: errors[idx])
        candidates.append((angles[best_idx], errors[best_idx]))

    if not candidates:
        min_idx = np.argmin(errors)
        return angles[min_idx]

    # Choose the candidate closest to 0 degrees
    best = min(candidates, key=lambda x: min(x[0], 360 - x[0]))
    return best[0]


def get_contour_info(contour_data: ContourData, base_contour_kd_tree, include_contour=False):
    contour = contour_data.contour
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
