import numpy as np

def cal_z_3_regression_param(points, heights):
    w = len(points[0])
    h = len(points[0][0])
    data = np.zeros((w, h, 2, 4))

    for i in range(w):
        for j in range(h):
            X = []
            Y = []
            Z = []
            for k in range(len(heights)):
                z = heights[k]
                print(z, points[k][i][j])
                X.append(points[k][i][j][0])
                Y.append(points[k][i][j][1])
                Z.append([z ** 3, z ** 2, z, 1])
            model_x_np = np.linalg.lstsq(Z, X, rcond=None)[0]
            model_y_np = np.linalg.lstsq(Z, Y, rcond=None)[0]
            pred_x = model_x_np.dot(np.array(Z).T)
            pred_y = model_y_np.dot(np.array(Z).T)
            for k in range(len(heights)):
                z = heights[k]
                print(z, points[k][i][j], pred_x[k], pred_y[k])
            data[i, j, 0] = model_x_np
            data[i, j, 1] = model_y_np
    return data
