import numpy as np

DPMM = 5
T_PAD = 876
B_PAD = 876
L_PAD = 1168
R_PAD = 1168
CHESSBORAD = (48, 36)
PERSPECTIVE_SPLIT = (15, 15)

# Currently using fixed regression coefficients derived from 3rd-order polynomial regression with variables x, y, and z.
# Assuming all cameras of the same model from Ador sharing the same coefficients.
reg_coeff_x = np.array([
    6.93391204e+01, 9.63563189e-01, -1.91665489e-02, -1.24325863e+01,
    4.82931219e-06, 9.06580887e-06, 4.63075822e-03, 3.28563742e-06,
    -3.46764674e-04, -1.39757522e-01, -2.89798314e-10, -8.04764814e-10,
    -6.00039622e-08, -1.11092487e-09, 1.22918275e-07, 3.47430090e-05,
    -1.26741281e-11, -6.21446113e-09, 1.42159717e-07, 5.75238359e-04,
])
reg_coeff_y = np.array([
    5.27510453e+01, -1.00202305e-02, 9.66854485e-01, -1.05937261e+01,
    1.30929307e-06, 5.50763312e-06, 4.82918209e-05, 6.65208015e-06,
    4.03374612e-03, -7.28522336e-02, -6.30330232e-11, -3.44119622e-10,
    8.51651642e-09, -6.31062758e-10, -6.82676833e-08, 1.04903699e-06,
    -8.30479429e-10, 1.31813358e-07, 3.77897893e-05, -3.79330973e-04,
])
