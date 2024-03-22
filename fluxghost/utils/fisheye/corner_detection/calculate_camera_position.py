import numpy as np

from .constants import S, H
from ..utils import linear_regression

def calculate_camera_position(data, rotation_matrix=np.eye(3), fix_hy=False):
    Ax = []
    Bx = []
    Ay = []
    By = []

    for i, (height, position, ref_height, ref_positon) in enumerate(data):
        dh = height - ref_height
        dx_h, dy_h, dz_h = np.matmul(rotation_matrix, [0, 0, dh])
        ref_x, ref_y = ref_positon
        dx = position[0] - ref_x
        dy = position[1] - ref_y
        Ax.append([dz_h, dx - S * dx_h])
        Bx.append([ref_x * dz_h + dx * dz_h])
        if fix_hy:
            Ay.append([dz_h])
            By.append([ref_y * dz_h + dy * dz_h - H * (dy - S * dy_h)])
        else:
            Ay.append([dz_h, dy - S * dy_h])
            By.append([ref_y * dz_h + dy * dz_h])
    Ax = np.array(Ax)
    Bx = np.array(Bx)
    Ay = np.array(Ay)
    By = np.array(By)
    X, r2x, _ = linear_regression(Ax, Bx)
    Y, r2y, _ = linear_regression(Ay, By)
    x_center, h_x, s_x = X[0][0], X[1][0], S
    y_center, h_y, s_y = Y[0][0], Y[1][0] if not fix_hy else H, S
    return x_center, y_center, h_x, h_y, s_x, s_y
