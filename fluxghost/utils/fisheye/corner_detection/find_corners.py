import cv2
import numpy as np


# Use Shi-Tomasi corner detector to find corners
def find_corners(img, max_corners, min_distance=30, quality_level=0.01, draw=False):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    corners = cv2.goodFeaturesToTrack(
        gray,
        maxCorners=max_corners,
        qualityLevel=quality_level,
        minDistance=min_distance,
    )
    corners = corners.reshape(-1, 2)

    new_corners = []
    cornerSubPixCriteria = (
        cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER,
        100,
        0.001,
    )
    for c in corners:
        j, i = c
        p = np.float32([[j, i]])
        cv2.cornerSubPix(gray, p, (8, 8), (-1, -1), cornerSubPixCriteria)
        new_corners.append(p[0])
    corners = np.array(new_corners)

    if draw:
        for corner in corners:
            x, y = corner
            x = int(x)
            y = int(y)
            cv2.circle(img, (x, y), 3, (0, 0, 255), 1)
            cv2.circle(img, (x, y), 0, (0, 0, 255), 1)
    return corners
