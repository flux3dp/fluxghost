import logging

import cv2
import numpy as np

from . import get_charuco_board

logger = logging.getLogger(__file__)
IS_DEBUGGING = False


def detect_charuco_markers(image, board):
    detector = cv2.aruco.CharucoDetector(board)
    # Convert the image to grayscale
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # Detect markers in the image
    diamond_corners, diamond_ids, marker_corners, marker_ids = detector.detectBoard(gray)

    return diamond_corners, diamond_ids, marker_corners, marker_ids


def get_calibration_data_from_charuco(
    image, squares_x=15, squares_y=10, is_vertical=False, include_marker_corners=True
):
    board = get_charuco_board(squares_x, squares_y)
    diamond_corners, diamond_ids, marker_corners, marker_ids = detect_charuco_markers(image, board)

    if diamond_corners is None or diamond_ids is None:
        return None

    logger.info('Detected {} charuco markers.'.format(len(diamond_ids)))
    if IS_DEBUGGING:
        cv2.imwrite('charuco-detected-image.png', image.copy())
        cv2.aruco.drawDetectedMarkers(image, marker_corners, marker_ids)
        cv2.aruco.drawDetectedCornersCharuco(image, diamond_corners, diamond_ids)
        cv2.imwrite('charuco-detected.png', image)

    corners = board.getChessboardCorners()
    objp = corners[diamond_ids.flatten()].reshape(-1, 3).astype(np.float32)
    imgp = diamond_corners.reshape(-1, 2).astype(np.float32)

    # Decide orientation flip from diamond corners only (their order is well-defined).
    needs_flip = imgp[0][0] > imgp[-1][0]

    # Optionally append aruco marker corners (4 extra 2D-3D correspondences per marker).
    # Note: marker corners are typically less precise than charuco intersections.
    if include_marker_corners and marker_ids is not None and len(marker_ids) > 0:
        board_obj_points = board.getObjPoints()
        board_ids = board.getIds().flatten()
        id_to_idx = {int(i): k for k, i in enumerate(board_ids)}

        m_objp_list, m_imgp_list = [], []
        for i, mid in enumerate(marker_ids.flatten()):
            k = id_to_idx.get(int(mid))
            if k is None:
                continue
            m_objp_list.append(np.asarray(board_obj_points[k]).reshape(4, 3))
            m_imgp_list.append(marker_corners[i].reshape(4, 2))

        if m_objp_list:
            m_objp = np.concatenate(m_objp_list).astype(np.float32)
            m_imgp = np.concatenate(m_imgp_list).astype(np.float32)
            objp = np.concatenate([objp, m_objp])
            imgp = np.concatenate([imgp, m_imgp])
            logger.info('Added {} marker corner points.'.format(len(m_objp)))

    # Apply board-coord transforms to the combined objp so diamond and marker
    # corners stay consistent with each other.
    if is_vertical:
        max_x = np.max(objp[:, 0])
        objp[:, 0] = max_x - objp[:, 0]
        objp[:, [0, 1]] = objp[:, [1, 0]]

    # make sure the chessboard is in the right orientation
    if needs_flip:
        last_point = corners[-1]
        objp = -objp + last_point

    # found_ratio reflects diamond coverage of the board, independent of marker corners.
    found_ratio = len(diamond_ids) / len(corners)
    return imgp, objp, found_ratio
