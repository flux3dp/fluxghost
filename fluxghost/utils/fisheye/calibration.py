import logging
import re

import cv2
import numpy as np

from .general import pad_image

logger = logging.getLogger('utils.fisheye.calibration')

INIT_K = np.array(
    [
        [1.54510482e03, 0, 2.76446858e03],
        [0, 1.54360221e03, 2.18888949e03],
        [0, 0, 1],
    ]
)

INIT_D = np.array(
    [
        [0],
        [0.10819493],
        [0.06230879],
        [-0.13045471],
    ]
)


def get_remap_img(img, k, d):
    h, w = img.shape[:2]
    mapx, mapy = cv2.fisheye.initUndistortRectifyMap(k, d, np.eye(3), k, (w, h), cv2.CV_32FC1)
    img = cv2.remap(img, mapx, mapy, cv2.INTER_LINEAR)
    # img = cv2.fisheye.undistortImage(img, k, d, np.eye(3), k)
    return img


def remap_corners(corners, k, d):
    res = cv2.fisheye.undistortPoints(corners, k, d, np.eye(3), k)
    return res


def distort_points(corners, k, d):
    q = np.linalg.inv(k)
    corners = cv2.convertPointsToHomogeneous(corners).reshape(-1, 3)
    corners = np.matmul(q, corners.T).T
    corners = cv2.convertPointsFromHomogeneous(corners).reshape(-1, 1, 2)
    res = cv2.fisheye.distortPoints(corners, k, d)
    return res


CORNER_SUBPIX_CRIT = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 1e-3)


def corner_sub_pix(gray_image, corners):
    return cv2.cornerSubPix(gray_image, corners, (11, 11), (-1, -1), CORNER_SUBPIX_CRIT)


FIND_CHESSBOARD_FLAGS = cv2.CALIB_CB_ADAPTIVE_THRESH + cv2.CALIB_CB_NORMALIZE_IMAGE + cv2.CALIB_CB_FAST_CHECK


def do_find_chessboard(img, chessboard, downsize_ratio=1, try_denoise=True):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    if downsize_ratio > 1:
        height, width = img.shape[:2]
        downsized_img = cv2.resize(img, (width // downsize_ratio, height // downsize_ratio))
        downsized_gray = cv2.cvtColor(downsized_img, cv2.COLOR_BGR2GRAY)
    else:
        downsized_img = img
        downsized_gray = gray

    ret, corners = cv2.findChessboardCorners(downsized_gray, chessboard, FIND_CHESSBOARD_FLAGS)
    if ret:
        return gray, ret, corners * downsize_ratio

    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    downsized_gray = clahe.apply(downsized_gray)
    ret, corners = cv2.findChessboardCorners(downsized_gray, chessboard, FIND_CHESSBOARD_FLAGS)
    if not try_denoise:
        return gray, ret, (corners * downsize_ratio if ret else corners)
    if ret:
        return gray, ret, corners * downsize_ratio

    denoised = cv2.fastNlMeansDenoisingColored(downsized_img, None, 10, 10, 7, 21)
    downsized_gray = cv2.cvtColor(denoised, cv2.COLOR_BGR2GRAY)
    ret, corners = cv2.findChessboardCorners(downsized_gray, chessboard, FIND_CHESSBOARD_FLAGS)
    if ret:
        return gray, ret, corners * downsize_ratio

    downsized_gray = clahe.apply(downsized_gray)
    ret, corners = cv2.findChessboardCorners(downsized_gray, chessboard, FIND_CHESSBOARD_FLAGS)
    return gray, ret, (corners * downsize_ratio if ret else corners)


def find_chessboard(
    img, chessboard, downsize_ratio=1, do_subpix=True, try_denoise=True, try_remap=True, k=None, d=None
):
    gray, ret, corners = do_find_chessboard(img, chessboard, downsize_ratio=downsize_ratio, try_denoise=try_denoise)
    if ret:
        if do_subpix:
            corners = corner_sub_pix(gray, corners)
        return gray, ret, corners
    if not try_remap or k is None or d is None:
        return gray, ret, corners
    remap = get_remap_img(img, k, d)
    gray, ret, corners = do_find_chessboard(remap, chessboard, downsize_ratio=downsize_ratio, try_denoise=try_denoise)
    if ret:
        if do_subpix:
            corners = corner_sub_pix(gray, corners)
        corners = distort_points(corners, k, d)
        return gray, ret, corners
    return gray, False, None


# CALIB_FIX_K4 sometimes works better, maybe set flags according to the camera
CALIBRATION_FLAGS = cv2.fisheye.CALIB_RECOMPUTE_EXTRINSIC + cv2.fisheye.CALIB_CHECK_COND + cv2.fisheye.CALIB_FIX_K1
CALIBRATION_CRIT = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 200, 1e-5)


def calibrate_fisheye(objpoints, imgpoints, indices, size):
    if len(imgpoints) == 0:
        raise Exception('Failed to calibrate camera, no img points left behind')
    try:
        ret, k, d, rvecs, tvecs = cv2.fisheye.calibrate(
            objpoints, imgpoints, size, None, None, None, None, CALIBRATION_FLAGS, CALIBRATION_CRIT
        )
        return ret, k, d, rvecs, tvecs, indices
    except cv2.error as e:
        pattern = r'CALIB_CHECK_COND - Ill-conditioned matrix for input array (\d+)'
        match = re.search(pattern, e.err)
        if match:
            error_array_number = int(match.group(1))
            new_objpoints = objpoints[:error_array_number] + objpoints[error_array_number + 1 :]
            new_imgpoints = imgpoints[:error_array_number] + imgpoints[error_array_number + 1 :]
            indices = indices[:error_array_number] + indices[error_array_number + 1 :]
            return calibrate_fisheye(new_objpoints, new_imgpoints, indices, size)
        raise e


# Calibrate using cv2.fisheye.calibrate
def calibrate_fisheye_camera(imgs, img_heights, chessboard, progress_callback=None, init_k=INIT_K, init_d=INIT_D):
    objp = np.zeros((chessboard[0] * chessboard[1], 1, 3), np.float64)
    objp[:, :, :2] = np.mgrid[0 : chessboard[0], 0 : chessboard[1]].T.reshape(-1, 1, 2) * 10
    objpoints = []  # 3d point in real world space
    imgpoints = []  # 2d points in image plane.
    heights = []
    for i in range(len(imgs)):
        if progress_callback:
            progress_callback(i / len(imgs))
        h = img_heights[i]
        img = imgs[i]
        img = pad_image(img)
        gray, ret, corners = find_chessboard(img, chessboard, 2, do_subpix=True, try_denoise=False, k=init_k, d=init_d)
        if ret:
            logger.info('found corners for idx {}, height {}'.format(i, h))
            objp = objp.copy()
            objp[:, :, 2] = -h
            objpoints.append(objp)
            imgpoints.append(corners)
            heights.append(h)
        else:
            logger.info('unable to find corners for idx {}, height {}'.format(i, h))
    best_result = None
    try:
        ret, k, d, rvecs, tvecs, res_heights = calibrate_fisheye(objpoints, imgpoints, heights, gray.shape[::-1])
        logger.info('Calibrate All imgs: {}'.format(ret))
        if ret < 5:
            return ret, k, d, rvecs, tvecs, res_heights
        best_result = (ret, k, d, rvecs, tvecs, res_heights)
    except Exception:
        logger.info('Calibrate All imgs failed')
    for i in range(len(heights)):
        try:
            h = heights[i]
            ret, k, d, rvecs, tvecs, _ = calibrate_fisheye([objpoints[i]], [imgpoints[i]], [h], gray.shape[::-1])
            logger.info('Calibrate {}: {}'.format(h, ret))
            if not best_result or ret < best_result[0]:
                best_result = (ret, k, d, rvecs, tvecs, [h])
        except Exception:
            logger.info('Failed to find matrix for img {}'.format(i))
    if not best_result:
        raise Exception('Failed to calibrate camera, no img points left behind')
    ret, k, d, rvecs, tvecs, heights = best_result
    logger.info('Calibration res: ret: {}\nK: {}\nD: {}'.format(ret, k, d))
    return ret, k, d, rvecs, tvecs, heights
