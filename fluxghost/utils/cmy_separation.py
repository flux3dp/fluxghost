"""RGB to CMY separation for printing without the black cartridge.

Beam Studio full color layers normally separate through the Fogra39 profile, which
generates a K channel. lcms has no switch to skip black generation, so we invert the
profile ourselves: sample every CMY ink combination with K pinned to 0, and for each
node of an sRGB grid keep the combination whose Lab is the closest match. The result
is baked into a 3D lookup table that Pillow applies in C.

Deep shadows are the one place this cannot follow the profile: CMY at 300% ink only
reaches L* ~= 20, so blacks come out as a dark brown grey. Everything else lands
within about 1.5 dE of the normal four colour separation.
"""

import logging

import numpy as np
from PIL import Image, ImageCms, ImageFilter
from scipy.spatial import cKDTree

logger = logging.getLogger('UTILS.CMY')

CMYK_PROFILE = 'static/Coated_Fogra39L_VIGC_300.icc'
LUT_SIZE = 33  # sRGB nodes per axis, the usual size for an ICC device link
INK_STEPS = 41  # candidate ink levels per channel

_lut = None
_black_ramp = None


def _to_lab(image, transform):
    raw = np.array(ImageCms.applyTransform(image, transform)).reshape(-1, 3)
    # PIL keeps L* as 0-255 and a*/b* as signed bytes
    return np.stack(
        [
            raw[:, 0].astype(np.float32) * 100 / 255,
            raw[:, 1].astype(np.int8).astype(np.float32),
            raw[:, 2].astype(np.int8).astype(np.float32),
        ],
        axis=1,
    )


def _cmy_candidates(cmyk_to_lab):
    """Every CMY ink combination with no black, indexed by Lab so we can look one up by colour."""
    inks = np.linspace(0, 255, INK_STEPS).round().astype(np.uint8)
    grid = np.array(np.meshgrid(inks, inks, inks, indexing='ij')).reshape(3, -1).T
    candidates = np.concatenate([grid, np.zeros((len(grid), 1), np.uint8)], axis=1)

    return grid, cKDTree(_to_lab(Image.fromarray(candidates.reshape(1, -1, 4), 'CMYK'), cmyk_to_lab))


def _cmyk_to_lab_transform():
    return ImageCms.buildTransform(
        ImageCms.getOpenProfile(CMYK_PROFILE), ImageCms.createProfile('LAB'), 'CMYK', 'LAB'
    )


def _build_lut():
    srgb = ImageCms.createProfile('sRGB')
    lab = ImageCms.createProfile('LAB')
    rgb_to_lab = ImageCms.buildTransform(srgb, lab, 'RGB', 'LAB')
    grid, tree = _cmy_candidates(_cmyk_to_lab_transform())

    nodes = np.linspace(0, 255, LUT_SIZE).round().astype(np.uint8)
    # Color3DLUT reads the table with red changing fastest, so build it blue major
    bgr = np.array(np.meshgrid(nodes, nodes, nodes, indexing='ij')).reshape(3, -1).T
    rgb = np.ascontiguousarray(bgr[:, ::-1])
    node_lab = _to_lab(Image.fromarray(rgb.reshape(1, -1, 3), 'RGB'), rgb_to_lab)
    _, nearest = tree.query(node_lab, workers=-1)
    table = grid[nearest].astype(np.float32) / 255

    return ImageFilter.Color3DLUT(LUT_SIZE, table.reshape(-1).tolist())


def _build_black_ramp():
    cmyk_to_lab = _cmyk_to_lab_transform()
    grid, tree = _cmy_candidates(cmyk_to_lab)
    levels = np.zeros((256, 4), dtype=np.uint8)
    levels[:, 3] = np.arange(256)
    black_lab = _to_lab(Image.fromarray(levels.reshape(1, -1, 4), 'CMYK'), cmyk_to_lab)
    _, nearest = tree.query(black_lab, workers=-1)

    return grid[nearest].astype(np.uint16)


def cmyk_to_cmy(image: Image.Image) -> Image.Image:
    """Move the black channel of a CMYK image into CMY, leaving C, M and Y as the file authored them.

    A CMYK file carries the separation its author chose, so re-separating it by colour would turn a
    pure cyan into a three ink mix. Only the black is replaced, by the CMY that reproduces that black
    level on its own, combined with the ink already there the way two inks overlap on paper.
    """
    global _black_ramp

    if _black_ramp is None:
        _black_ramp = _build_black_ramp()
        logger.info('Built black to CMY ramp')
    channels = np.array(image)
    base = channels[:, :, :3].astype(np.uint16)
    added = _black_ramp[channels[:, :, 3]]
    cmy = (base + added - base * added // 255).astype(np.uint8)
    bands = [Image.fromarray(cmy[:, :, i], 'L') for i in range(3)]

    return Image.merge('CMYK', (*bands, Image.new('L', image.size, 0)))


def rgb_to_cmy(image: Image.Image) -> Image.Image:
    """Separate an RGB image into a CMYK image that never uses black ink."""
    global _lut

    if _lut is None:
        _lut = _build_lut()
        logger.info('Built RGB to CMY lookup table')
    cmy = image.filter(_lut)
    return Image.merge('CMYK', (*cmy.split(), Image.new('L', image.size, 0)))
