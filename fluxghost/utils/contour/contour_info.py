import cv2
import numpy as np


def get_contour_info(contour):
    data_pts = np.array(contour, dtype=np.float64).reshape((-1, 2))
    mean, eigenvectors, eigenvalues = cv2.PCACompute2(data_pts, mean=np.empty((0)))
    center = tuple(mean[0])
    angle = np.arctan2(eigenvectors[0, 1], eigenvectors[0, 0])
    bbox = cv2.boundingRect(contour)
    return {'center': center, 'angle': angle, 'bbox': bbox}
