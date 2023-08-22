import cv2
import numpy as np

from .calibration import corner_sub_pix, find_corners, get_remap_img
from .constants import DPMM
from .general import pad_image


def get_split_indices(split, chessboard, i, j):
    split_x, split_y = split
    l = (i * chessboard[0]) // split_x
    r = min(((i + 1) * chessboard[0]) // split_x, chessboard[0] - 1)
    t = (j * chessboard[1]) // split_y
    b = min(((j + 1) * chessboard[1]) // split_y, chessboard[1] - 1)
    return l, r, t, b


def get_all_split_indices(split, chessboard):
    split_x, split_y = split
    table = np.array([[None for _ in range(split_y + 1)] for _ in range(split_x + 1)])
    for i in range(split_x + 1):
        for j in range(split_y + 1):
            table[i][j] = [
                min(i * chessboard[0] // split_x, chessboard[0] - 1),
                min(j * chessboard[1] // split_y, chessboard[1] - 1),
            ]
    return table


def get_perspective_points(img, k, d, split, chessboard):
    img = pad_image(img)
    img = get_remap_img(img, k, d)
    gray, ret, corners = find_corners(img, chessboard, 2)
    if not ret:
        raise Exception('Cannot find corners')
    corners = corner_sub_pix(gray, corners)
    corners = np.reshape(corners, chessboard[::-1] + (2,))
    split_x, split_y = split
    table = get_all_split_indices(split, chessboard)
    for i in range(split_x + 1):
        for j in range(split_y + 1):
            table[i][j] = corners[table[i][j][1]][table[i][j][0]].tolist()
    return np.array(table)


def apply_perspective_points_transform(img, k, d, split, chessboard, points):
    img = pad_image(img)
    img = get_remap_img(img, k, d)

    padding = 100
    split_x, split_y = split

    # 10mm each chessboard square
    unit_length = DPMM * 10
    img_w = (chessboard[0] - 1) * unit_length + padding * 2
    img_h = (chessboard[1] - 1) * unit_length + padding * 2
    base_img = np.zeros((img_h, img_w, 3), np.uint8)
    split_indice = get_all_split_indices(split, chessboard)
    for i in range(split_x):
        for j in range(split_y):
            lt = points[i][j]
            rt = points[i + 1][j]
            lb = points[i][j + 1]
            rb = points[i + 1][j + 1]
            src_points = np.float32([lt, rt, lb, rb])

            l, t = split_indice[i][j]
            r, b = split_indice[i + 1][j + 1]
            dst_w = (r - l) * unit_length
            dst_h = (b - t) * unit_length
            dst_l = padding if i == 0 else 0
            dst_t = padding if j == 0 else 0
            dst_points = np.float32([
                [dst_l, dst_t],
                [dst_l + dst_w, dst_t],
                [dst_l, dst_t + dst_h],
                [dst_l + dst_w, dst_t + dst_h],
            ])
            perspective_matrix = cv2.getPerspectiveTransform(src_points, dst_points)

            # draw the perspective transformation to the input image, padding img at edges
            draw_w, draw_h = dst_w, dst_h
            if i == 0 or i == split_x - 1:
                draw_w += padding if split_x > 1 else padding * 2
            if j == 0 or j == split_y - 1:
                draw_h += padding if split_y > 1 else padding * 2
            out = cv2.warpPerspective(img, perspective_matrix, (draw_w, draw_h))

            img_l = 0 if l == 0 else l * unit_length + padding
            img_t = 0 if t == 0 else t * unit_length + padding
            base_img[img_t:img_t + draw_h, img_l:img_l + draw_w] = out
    return base_img
