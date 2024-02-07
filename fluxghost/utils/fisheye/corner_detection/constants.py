def get_grid(version):
    if version == 2:
        return (
            [0, 10] + [x for x in range(20, 411, 30)] + [420, 430],
            [0, 10, 20] + [y for y in range(30, 301, 30)],
        )
    raise ValueError('Invalid version')

def get_ref_point_indices(version):
    if version == 2:
        return (5, 7), (5, 10), (9, 7), (9, 10), (6, 8), (6, 9), (8, 8), (8, 9)
    raise ValueError('Invalid version')

# init parameters for pitch 0
H = 200
IMG_CENTER = (2800, 2250)
S = 6
