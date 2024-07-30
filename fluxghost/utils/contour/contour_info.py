import math

import cv2
import numpy as np


def get_contour_info(contour, base_flip_info=None):
    data_pts = np.array(contour, dtype=np.float64).reshape((-1, 2))
    mean, eigenvectors, _ = cv2.PCACompute2(data_pts, mean=np.empty((0)))
    center = tuple(mean[0])
    angle = np.arctan2(eigenvectors[0, 1], eigenvectors[0, 0])
    bbox = cv2.boundingRect(contour)

    # calculate the moment along the angle
    # determine to add 180 degree to the angle or not
    c, s = math.cos(-angle), math.sin(-angle)
    rotation_matrix = np.array([[c, -s], [s, c]])
    rotated = data_pts - mean
    rotated = np.dot(rotated, rotation_matrix.T)
    rotated = rotated + mean
    new_contour = rotated.reshape((-1, 1, 2)).astype(np.int32)
    moment = cv2.moments(new_contour)
    flip_info = [moment['nu03'], moment['nu30'], moment['nu21'], moment['nu12']]
    for i in range(len(flip_info)):
        if abs(flip_info[i]) < 0.001:
            flip_info[i] = 0
        else:
            flip_info[i] = 1 if flip_info[i] > 0 else -1
    if base_flip_info is not None:
        score = 0
        for i in range(len(flip_info)):
            score += abs(flip_info[i] - base_flip_info[i])
        if score > 4:
            angle = math.atan2(-eigenvectors[0, 1], -eigenvectors[0, 0])
    return {'center': center, 'angle': angle, 'bbox': bbox}, flip_info
