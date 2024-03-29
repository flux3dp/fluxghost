def get_grid(version):
    if version == 2:
        return (
            [0, 10] + [x for x in range(20, 411, 30)] + [420, 430],
            [0, 10, 20] + [y for y in range(30, 271, 30)] + [290],
        )
    raise ValueError('Invalid version')

def get_ref_points(version):
    if version == 2:
        ref_points = [(170, 90), (260, 90), (170, 180), (260, 180), (200, 120),(230, 120), (200, 150), (230, 150)]
        return ref_points
    raise ValueError('Invalid version')

# init parameters for pitch 0
H = 200
IMG_CENTER = (2800, 2250)
S = 6
