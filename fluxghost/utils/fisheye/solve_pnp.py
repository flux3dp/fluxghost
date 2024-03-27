import cv2
import numpy as np

# cv2.fisheye.solvePnP is implemented in OpenCV 4.10.0, so we need to implement it ourselves before 4.10.0 release
def solve_pnp(
    objpoints,
    imgpoints,
    k,
    d,
    useExtrinsicGuess=False,
    flags=cv2.SOLVEPNP_ITERATIVE,
    criteria=(cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 1e-8),
):
    normalized_img_points = cv2.fisheye.undistortPoints(imgpoints, k, d, np.eye(3), k, criteria=criteria)
    return cv2.solvePnP(objpoints, normalized_img_points, k, None, None, None, useExtrinsicGuess=useExtrinsicGuess, flags=flags)
