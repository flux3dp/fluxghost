def get_grid(version):
    if version == 2:
        return (
            [0, 10] + [x for x in range(20, 411, 30)] + [420, 430],
            [0, 10, 20] + [y for y in range(30, 271, 30)] + [290],
        )
    raise ValueError('Invalid version')


def get_ref_points(version):
    if version == 2:
        ref_points = [(155, 90), (275, 90), (155, 210), (275, 210), (185, 120), (245, 120), (185, 180), (245, 180)]
        return ref_points
    raise ValueError('Invalid version')


# init parameters for pitch 0
H = 200
IMG_CENTER = (2800, 2250)
S = 6
