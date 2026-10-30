import cv2
import numpy as np
from scipy.interpolate import RegularGridInterpolator

from .calibration import get_remap_img, project_points, remap_corners
from .constants import DPMM
from .general import pad_image

# Manual per-region offsets ramp across a band this fraction of a region wide, centred on each border,
# and hold the exact value over the rest of the region (Beam Studio PRD manual-calibration-config D8).
REGION_OFFSET_BLEND_BAND = 1 / 3
REGION_KEYS = ['topLeft', 'top', 'topRight', 'left', 'center', 'right', 'bottomLeft', 'bottom', 'bottomRight']


def region_offset_sampler(table, band=REGION_OFFSET_BLEND_BAND):
    """
    Plateau-and-ramp surface over a 3x3 table as a callable `f((ty, tx)) -> (ox, oy)`, coordinates in region
    units [0, 3]. Each cell is duplicated at both ends of its plateau, so plain bilinear interpolation over
    the knots gives the exact cell value over the middle `1 - band` of a region, a linear ramp across the
    band at each border (a border = midpoint of its neighbours) and no ramp at the bed edges.
    """
    h = band / 2
    knots = [0, 1 - h, 1 + h, 2 - h, 2 + h, 3]
    values = np.repeat(np.repeat(np.asarray(table, np.float64), 2, axis=0), 2, axis=1)
    return RegularGridInterpolator((knots, knots), values, bounds_error=False, fill_value=None)


def get_split_indices(split, chessboard, i, j):
    split_x, split_y = split
    l = (i * chessboard[0]) // split_x  # noqa: E741
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


def generate_grid_objects(grid_data_x, grid_data_y):
    x_start, x_end, x_step = grid_data_x
    y_start, y_end, y_step = grid_data_y
    xgrid = np.arange(x_start, x_end + 1, x_step)
    if xgrid[-1] != x_end:
        xgrid = np.append(xgrid, x_end)
    ygrid = np.arange(y_start, y_end + 1, y_step)
    if ygrid[-1] != y_end:
        ygrid = np.append(ygrid, y_end)
    xx, yy = np.meshgrid(xgrid, ygrid)
    objp = np.dstack([xx, yy, np.zeros_like(xx)])

    return xgrid, ygrid, objp


def calculate_regional_perspective_points(
    grid_data_x,
    grid_data_y,
    h,
    k,
    d,
    rvecs,
    tvecs,
    is_fisheye=True,
    total_width=None,
    total_height=None,
    offset=(0, 0),
    region_offsets=None,
):
    """
    Calculate the perspective points using for 9-region rvecs and tvecs
    region keys: ['topLeft', 'top', 'topRight', 'left', 'center', 'right', 'bottomLeft', 'bottom', 'bottomRight']

    :param int[] grid_data_x: (x_start, x_end, x_step)
    :param int[] grid_data_y: (y_start, y_end, y_step)
    :param float h: height of the camera
    :param np.array k: camera matrix
    :param np.array d: distortion coefficients
    :param Dict[np.array] rvecs: of rotation vectors for each region
    :param Dict[np.array] tvecs: dict of translation vectors for each region
    :param (float, float) offset: manual bed-plane correction in mm added to every object point before
        projection, so the warped image shifts by exactly that much on the bed
    :param Dict[(float, float)] region_offsets: per-region override of `offset`; the region is chosen from
        the unshifted point, so a cell means "pixels shown in this part of the bed move by this much".
        Its optional `blend` key (default True) samples the table as a plateau-and-ramp surface (exact over
        the middle of each region, linear across a REGION_OFFSET_BLEND_BAND-wide band at each border)
        instead of stepping at the border, so neighbouring regions with different offsets do not tear
    """
    xgrid, ygrid, objp = generate_grid_objects(grid_data_x, grid_data_y)
    orig_shape = objp.shape
    objp = objp.reshape(-1, 3)
    perspective_points = np.zeros((objp.shape[0], 2), np.float32)
    region_key_map = REGION_KEYS
    if total_width is None:
        total_width = xgrid[-1] - xgrid[0]
    if total_height is None:
        total_height = ygrid[-1] - ygrid[0]
    # bed coordinates in region units [0, 3]
    tx = (objp[:, 0] - xgrid[0]) * 3 / total_width
    ty = (objp[:, 1] - ygrid[0]) * 3 / total_height
    blended = None
    if region_offsets and region_offsets.get('blend', True):
        table = [[region_offsets.get(region_key_map[r * 3 + c], offset) for c in range(3)] for r in range(3)]
        blended = region_offset_sampler(table)(np.stack([ty, tx], axis=-1))
    for i in range(objp.shape[0]):
        x, y = objp[i][0], objp[i][1]
        x_index = min(int(tx[i]), 2)
        y_index = min(int(ty[i]), 2)
        region = region_key_map[y_index * 3 + x_index]
        rvec = rvecs[region]
        tvec = tvecs[region]
        if blended is not None:
            ox, oy = blended[i]
        elif region_offsets:
            ox, oy = region_offsets.get(region, offset)
        else:
            ox, oy = offset
        point = project_points(
            np.array([[x + ox, y + oy, -h]]).reshape(-1, 1, 3).astype(np.float32),
            rvec,
            tvec,
            k,
            d,
            is_fisheye=is_fisheye,
        )
        perspective_points[i] = point[0][0]
    perspective_points = perspective_points.reshape(1, -1, 2)
    perspective_points = remap_corners(perspective_points, k, d, is_fisheye=is_fisheye).reshape(
        orig_shape[0], orig_shape[1], 2
    )

    return perspective_points, xgrid, ygrid


def apply_perspective_points_transform(img, k, d, split, chessboard, points, downsample=1, is_fisheye=True):
    if is_fisheye:
        img = pad_image(img)
    if downsample > 1:
        img = cv2.resize(img, (img.shape[1] // downsample, img.shape[0] // downsample))
        k = k.copy()
        k[0][0] /= downsample
        k[1][1] /= downsample
        k[0][2] /= downsample
        k[1][2] /= downsample
        img = get_remap_img(img, k, d, is_fisheye=is_fisheye)
        img = cv2.resize(img, (img.shape[1] * downsample, img.shape[0] * downsample))
    else:
        img = get_remap_img(img, k, d, is_fisheye=is_fisheye)

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

            l, t = split_indice[i][j]  # noqa: E741
            r, b = split_indice[i + 1][j + 1]
            dst_w = (r - l) * unit_length
            dst_h = (b - t) * unit_length
            dst_l = padding if i == 0 else 0
            dst_t = padding if j == 0 else 0
            dst_points = np.float32(
                [
                    [dst_l, dst_t],
                    [dst_l + dst_w, dst_t],
                    [dst_l, dst_t + dst_h],
                    [dst_l + dst_w, dst_t + dst_h],
                ]
            )
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
            base_img[img_t : img_t + draw_h, img_l : img_l + draw_w] = out
    return base_img
