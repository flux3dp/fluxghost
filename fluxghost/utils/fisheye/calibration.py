import logging
import re

import cv2
import numpy as np

from .general import pad_image

logger = logging.getLogger('utils.fisheye.calibration')

INIT_K = np.array([
    [6.40004499e+03, 0, 2.81798089e+03],
    [0, 6.40710065e+03, 2.23585732e+03],
    [0, 0, 1],
])

INIT_D = np.array([
    [-5.22543279],
    [72.596491],
    [-792.55764606],
    [3614.92299842],
])

FIND_CHESSBOARD_FLAGS = cv2.CALIB_CB_ADAPTIVE_THRESH + cv2.CALIB_CB_NORMALIZE_IMAGE + cv2.CALIB_CB_FAST_CHECK
def find_corners(img, chessboard, downsize_ratio = 1, try_denoise = True):
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

CORNER_SUBPIX_CRIT = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 1e-3)
def corner_sub_pix(gray_image, corners):
    return cv2.cornerSubPix(gray_image, corners, (11, 11), (-1, -1), CORNER_SUBPIX_CRIT)

CALIBRATION_FLAGS = cv2.fisheye.CALIB_RECOMPUTE_EXTRINSIC + cv2.fisheye.CALIB_CHECK_COND + cv2.fisheye.CALIB_FIX_SKEW + cv2.fisheye.CALIB_FIX_K1
CALIBRATION_CRIT = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 200, 1e-5)
def calibrate_fisheye(objpoints, imgpoints, size):
    if len(imgpoints) == 0:
        raise Exception('Failed to calibrate camera, no img points left behind')
    try:
        ret, k, d, _, _ = cv2.fisheye.calibrate(objpoints, imgpoints, size, None, None, None, None, CALIBRATION_FLAGS, CALIBRATION_CRIT)
        return ret, k, d
    except cv2.error as e:
        pattern = r'CALIB_CHECK_COND - Ill-conditioned matrix for input array (\d+)'
        match = re.search(pattern, e.err)
        if match:
            error_array_number = int(match.group(1))
            new_objpoints = objpoints[:error_array_number] + objpoints[error_array_number + 1:]
            new_imgpoints = imgpoints[:error_array_number] + imgpoints[error_array_number + 1:]
            return calibrate_fisheye(new_objpoints, new_imgpoints, size)
        raise e

# Calibrate using cv2.fisheye.calibrate
def calibrate_fisheye_camera(imgs, chessboard, progress_callback):
    objp = np.zeros((chessboard[0] * chessboard[1], 1, 3), np.float64)
    objp[:, :, :2] = np.mgrid[0:chessboard[0], 0:chessboard[1]].T.reshape(-1, 1, 2)
    objpoints = [] # 3d point in real world space
    imgpoints = [] # 2d points in image plane.
    for i in range(len(imgs)):
        progress_callback(i / len(imgs))
        img = imgs[i]
        img = pad_image(img)
        gray, ret, corners = find_corners(img, chessboard, 2, False)
        if ret:
            logger.info('found corners for {}'.format(i))
            objpoints.append(objp)
            corners = corner_sub_pix(gray, corners)
            imgpoints.append(corners)
        else:
            logger.info('unable to find corners for {}'.format(i))
    best_result = None
    try:
        ret, k, d, = calibrate_fisheye(objpoints, imgpoints, gray.shape[::-1])
        logger.info('Calibrate All imgs:'.format(i, ret))
        best_result = (ret, k, d)
    except Exception:
        logger.info('Calibrate All imgs failed')
    for i in range(len(imgpoints)):
        try:
            ret, k, d, = calibrate_fisheye(objpoints[i: i+1], imgpoints[i: i+1], gray.shape[::-1])
            logger.info('Calibrate {}: {}'.format(i, ret))
            if not best_result:
                best_result = (ret, k, d)
            else:
                if ret < best_result[0]:
                    best_result = (ret, k, d)
        except Exception:
            logger.info('Failed to find matrix for img {}'.format(i))
            pass
    if not best_result:
        raise Exception('Failed to calibrate camera, no img points left behind')
    ret, k, d = best_result
    logger.info('Calibration res: ret: {}\nK: {}\nD: {}'.format(ret, k, d))
    if ret > 5:
        k = INIT_K.copy()
        d = INIT_D.copy()
        logger.warning('Calibration ret to big, using default K: {}, D: {}'.format(k, d))
    return k, d


def get_remap_img(img, k, d):
    h, w = img.shape[:2]
    mapx, mapy = cv2.fisheye.initUndistortRectifyMap(k, d, np.eye(3), k, (w, h), cv2.CV_32FC1)
    img = cv2.remap(img, mapx, mapy, cv2.INTER_LINEAR)
    return img
