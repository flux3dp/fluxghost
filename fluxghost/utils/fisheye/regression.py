import numpy as np

def get_reg_poly_arr(variables, add_intercept=True):
    x, y, z = variables
    return np.array(([1] if add_intercept else []) + [
            x, y, z,
            x ** 2, x * y, x * z,
            y ** 2, y * z, z ** 2,
            x ** 3, x ** 2 * y, x ** 2 * z,
            x * y ** 2, x * y * z, x * z ** 2,
            y ** 3, y ** 2 * z, y * z ** 2,
            z ** 3,
        ])

def apply_reg_coeff(variables, coeff_x, coeff_y):
    poly_vars = get_reg_poly_arr(variables)
    pred_x = np.dot(coeff_x, poly_vars)
    pred_y = np.dot(coeff_y, poly_vars)
    return pred_x, pred_y
