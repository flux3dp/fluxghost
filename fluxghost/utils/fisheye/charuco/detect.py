import logging

import cv2
import cv2.aruco as aruco
import numpy as np

from . import get_charuco_board

logger = logging.getLogger(__file__)
IS_DEBUGGING = False


def detect_charuco_markers(image, board):
    detector = aruco.CharucoDetector(board)
    # Convert the image to grayscale
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # Detect markers in the image
    diamond_corners, diamond_ids, marker_corners, marker_ids = detector.detectBoard(gray)

    return diamond_corners, diamond_ids, marker_corners, marker_ids


def get_calibration_data_from_charuco(image, squares_x=15, squares_y=10):
    board = get_charuco_board(squares_x, squares_y)
    diamond_corners, diamond_ids, marker_corners, marker_ids = detect_charuco_markers(image, board)

    if diamond_corners is not None and diamond_ids is not None:
        logger.info(f"Detected {len(diamond_ids)} charuco markers.")
        if IS_DEBUGGING:
            cv2.aruco.drawDetectedMarkers(image, marker_corners, marker_ids)
            cv2.aruco.drawDetectedCornersCharuco(image, diamond_corners, diamond_ids)
            cv2.imwrite('charuco-detected.png', image)
        objp = board.getChessboardCorners()[diamond_ids.flatten()].reshape(-1, 3).astype(np.float32)
        imgp = diamond_corners.reshape(-1, 2).astype(np.float32)

        # make sure the chessboard is in the right orientation
        if imgp[0][0] > imgp[-1][0]:
            last_point = board.getChessboardCorners()[-1]
            objp = -objp + last_point
        return imgp, objp
    else:
        return None
