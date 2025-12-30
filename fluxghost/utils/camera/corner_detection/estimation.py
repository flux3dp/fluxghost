import functools


def get_origin_p0():
    return 590, 550  # h = 0


def get_origin_point_pitch_20():
    return 850, 330


# Guessing origin point for images
@functools.lru_cache(maxsize=20)
def get_origin(with_pitch=False):
    if with_pitch:
        return get_origin_point_pitch_20()
    else:
        return get_origin_p0()


def get_pixel_ratio_p0(x, y):
    # data from h = 0
    x_ratio = (215 - x) / 215
    xr = -1.8 * abs(x_ratio) + 6
    xyr = x_ratio * (17 / 3000 * y - 0.8)
    return xr, 4.8, 0, xyr


def get_pixel_ratio_pitch_20(x, y):
    x_ratio = (215 - x) / 215
    abs_x_ratio = abs(x_ratio)
    y_ratio = y / 300
    xr = (1 - y_ratio) * (3 * abs_x_ratio + 3.9 * (1 - abs_x_ratio)) + y_ratio * (
        4.3 * abs_x_ratio + 6.3 * (1 - abs_x_ratio)
    )
    xyr = (1 - y_ratio) * (-0.45 * x_ratio) + y_ratio * (0.3 * x_ratio)
    yr = (1 - y_ratio) * 2.2 + y_ratio * 5.1
    yxr = (1 - y_ratio) * -1.1 + y_ratio * -1.3
    return xr, yr, yxr, xyr


# Guessing pixel ration for images
@functools.lru_cache(maxsize=20)
def get_pixel_ratio(x, y, with_pitch=False):
    if with_pitch:
        return get_pixel_ratio_pitch_20(x, y)
    else:
        return get_pixel_ratio_p0(x, y)
