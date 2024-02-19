import numpy as np

from .constants import H, IMG_CENTER, S

# estimate point position after height change
def estimate_point(point, dh, rotation_matrix=np.eye(3), x_center=IMG_CENTER[0], y_center=IMG_CENTER[1], h_x=H, h_y=H, s_x=S, s_y=S):
    dx_h, dy_h, dz_h = np.matmul(rotation_matrix, [0, 0, dh])
    x, y = point
    x_rel = x - x_center
    y_rel = y - y_center
    dx = (x_rel * dz_h + dx_h * s_x * h_x) / (h_x - dz_h)
    dy = (y_rel * dz_h + dy_h * s_y * h_y) / (h_y - dz_h)
    new_x = x + dx
    new_y = y + dy
    return np.array([new_x, new_y])
