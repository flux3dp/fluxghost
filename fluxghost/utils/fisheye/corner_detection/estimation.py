import functools


def get_origin_p0(h, remapped=False):
    return 550, 500  # h = 0


def get_origin_point_pitch_20(h, remapped=False):
    raise NotImplementedError

# Guessing origin point for images
@functools.lru_cache(maxsize=20)
def get_origin(h, remapped=False, with_pitch=False):
    if with_pitch:
        return get_origin_point_pitch_20(h, remapped)
    else:
        return get_origin_p0(h, remapped)


def get_pixel_ratio_p0(h, x, y, remapped=False):
    # data from h = 0
    x_ratio = (215 - x) / 215
    xr = -2 * abs(x_ratio) + 6
    xyr = x_ratio * (17 / 3000 * y - 0.8)
    return xr, 4.8, 0, xyr

def get_pixel_ratio_pitch_20(h, x, y, remapped=False):
    raise NotImplementedError

# Guessing pixel ration for images
@functools.lru_cache(maxsize=20)
def get_pixel_ratio(h, x, y, remapped=False, with_pitch=False):
    if with_pitch:
        return get_pixel_ratio_pitch_20(h, x, y, remapped)
    else:
        return get_pixel_ratio_p0(h, x, y, remapped)
