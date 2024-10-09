import warnings
# version 2: ado1
# version 3: fbb2

def get_grid(version):
    if version == 2:
        return (
            [0, 10] + [x for x in range(20, 411, 30)] + [420, 430],
            [0, 10, 20] + [y for y in range(30, 271, 30)] + [290],
        )
    raise ValueError('Invalid version')


def get_ref_points(version):
    warnings.warn('get_ref_points is deprecated', DeprecationWarning)
    if version == 2:
        return [(155, 90), (275, 90), (155, 210), (275, 210), (185, 120), (245, 120), (185, 180), (245, 180)]
    if version == 3:
        return [(-60, 10), (60, 10), (-60, 90), (60, 90), (-30, 30), (30, 30), (-30, 70), (30, 70)]
    raise ValueError('Invalid version')


# init parameters for pitch 0
H = 200
IMG_CENTER = (2800, 2250)
S = 6
