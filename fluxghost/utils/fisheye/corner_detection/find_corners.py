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

def find_blob_centers(img, min_threshold=10, max_threshold=200 , min_area=15, max_area=1000, min_circularity=0.64, max_circularity=None, min_convexity=0.85, max_convexity=None, filterByColor=False, blobColor=255, draw=False):
    '''
    Find blob centers in an image using OpenCV's SimpleBlobDetector.
    '''
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    params = cv2.SimpleBlobDetector_Params()

    params.filterByColor = filterByColor
    if filterByColor:
        params.blobColor = blobColor

    if min_threshold is not None:
        params.minThreshold = min_threshold
    if max_threshold is not None:
        params.maxThreshold = max_threshold

    if min_area is not None or max_area is not None:
        params.filterByArea = True
        if min_area is not None:
            params.minArea = min_area
        if max_area is not None:
            params.maxArea = max_area

    if min_circularity is not None or max_circularity is not None:
        params.filterByCircularity = True
        if min_circularity is not None:
            params.minCircularity = min_circularity
        if max_circularity is not None:
            params.maxCircularity = max_circularity

    if min_convexity is not None or max_convexity is not None:
        params.filterByConvexity = True
        if min_convexity is not None:
            params.minConvexity = min_convexity
        if max_convexity is not None:
            params.maxConvexity = max_convexity

    detector = cv2.SimpleBlobDetector_create(params)
    keypoints = detector.detect(gray)
    centers = np.array([keypoint.pt for keypoint in keypoints])

    if draw:
        cv2.drawKeypoints(gray, keypoints, np.array([]), (0, 0, 255), cv2.DRAW_MATCHES_FLAGS_DRAW_RICH_KEYPOINTS)

    return centers
