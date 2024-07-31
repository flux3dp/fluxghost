import math

import cv2
import numpy as np


def get_rot_info(contour):
    moment = cv2.moments(contour)
    return np.array([moment['nu03'], moment['nu30'], moment['nu21'], moment['nu12']])


def get_contour_info(contour, base_rot_info=None):
    data_pts = np.array(contour, dtype=np.float64).reshape((-1, 2))
    mean, eigenvectors, _ = cv2.PCACompute2(data_pts, mean=np.empty((0)))
    center = tuple(mean[0])
    bbox = cv2.boundingRect(contour)

    moment = cv2.moments(contour)

    if moment["m00"] == 0:
        center = tuple(mean[0])
    else:
        cx = int(moment["m10"] / moment["m00"])
        cy = int(moment["m01"] / moment["m00"])
        center = (cx, cy)

    if base_rot_info is not None:
        # rotate the contour to the best angle (the angle that has the smallest difference with the base_rot_info)
        res = None
        for i in range(360):
            rad = i * math.pi / 180
            c, s = math.cos(-rad), math.sin(-rad)
            rotation_matrix = np.array([[c, -s], [s, c]])
            rotated = data_pts - mean
            rotated = np.dot(rotated, rotation_matrix.T)
            rotated = rotated + mean
            new_contour = rotated.reshape((-1, 1, 2)).astype(np.int32)
            rot_info = get_rot_info(new_contour)
            score = np.linalg.norm(rot_info - base_rot_info)
            if not res:
                res = score, rad, rot_info, new_contour
            elif score < res[0]:
                res = score, rad, rot_info, new_contour
        _, angle, rot_info, _ = res
    else:
        angle = np.arctan2(eigenvectors[0, 1], eigenvectors[0, 0])
        c, s = math.cos(-angle), math.sin(-angle)
        rotation_matrix = np.array([[c, -s], [s, c]])
        rotated = data_pts - mean
        rotated = np.dot(rotated, rotation_matrix.T)
        rotated = rotated + mean
        new_contour = rotated.reshape((-1, 1, 2)).astype(np.int32)
        rot_info = get_rot_info(new_contour)
    return {'center': center, 'angle': angle, 'bbox': bbox}, rot_info
