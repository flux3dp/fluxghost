import numpy as np

def linear_regression(A, B):
    X = np.linalg.inv(A.T.dot(A)).dot(A.T).dot(B)
    sst = np.sum((B - np.mean(B)) ** 2)
    sse = np.sum((B - A.dot(X)) ** 2)
    if sst != 0:
        r2 = 1 - sse / sst
    else:
        r2 = 1
    std = np.sqrt(sse / (len(B) - len(X)))
    return X, r2, std
