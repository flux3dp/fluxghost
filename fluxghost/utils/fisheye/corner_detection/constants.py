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


# init parameters for pitch 0
H = 200
IMG_CENTER = (2800, 2250)
S = 6
