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
    is_fisheye=True,
):
    return cv2.solvePnP(
        objpoints,
        cv2.fisheye.undistortPoints(imgpoints, k, d, np.eye(3), k) if is_fisheye else imgpoints,
        k,
        None if is_fisheye else d,
        None,
        None,
        useExtrinsicGuess=useExtrinsicGuess,
        flags=flags,
    )
