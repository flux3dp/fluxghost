import numpy as np


def calculate_3d_rotation_matrix(rx: float, ry: float, rz: float):
    Rx = np.array([
        [1, 0, 0],
        [0, np.cos(rx), -np.sin(rx)],
        [0, np.sin(rx), np.cos(rx)],
    ])
    Ry = np.array([
        [np.cos(ry), 0, np.sin(ry)],
        [0, 1, 0],
        [-np.sin(ry), 0, np.cos(ry)],
    ])
    Rz = np.array([
        [np.cos(rz), -np.sin(rz), 0],
        [np.sin(rz), np.cos(rz), 0],
        [0, 0, 1],
    ])
    return np.matmul(Rz, np.matmul(Ry, Rx))

def apply_matrix_to_perspective_points(points, matrix, height):
    # Calculated from average of 10 machines
    w_center = 2800
    h_center = 2230
    w, h = points.shape[:2]
    new_points = np.concatenate([points, height * np.ones((w, h, 1))], axis=2)
    new_points = new_points - [w_center, h_center, 0]
    new_points = new_points.reshape(-1, 3).T

    new_points = np.dot(matrix, new_points).T
    new_points = new_points.reshape(w, h, 3)
    interpolated_h = new_points[:, :, 2] / height
    new_points = np.dstack([new_points[:, :, 0] / interpolated_h,
                                 new_points[:, :, 1] / interpolated_h])
    new_points = new_points + [w_center, h_center]
    return new_points
