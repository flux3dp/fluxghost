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
    # Fisheye: solve in normalized coordinates. Re-projecting with P=k and then passing k to solvePnP is not a
    # round trip when k has a skew term (fisheye.undistortPoints applies P's skew, solvePnP ignores K's), which put
    # the pose off by a few tenths of a mm against project_points, whose distortion model has no skew either.
    return cv2.solvePnP(
        objpoints,
        cv2.fisheye.undistortPoints(imgpoints, k, d) if is_fisheye else imgpoints,
        np.eye(3) if is_fisheye else k,
        None if is_fisheye else d,
        None,
        None,
        useExtrinsicGuess=useExtrinsicGuess,
        flags=flags,
    )
