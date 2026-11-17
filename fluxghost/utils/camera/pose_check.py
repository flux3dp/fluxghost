"""Camera pose check for the auto full-area preview on fbb2 / fhx2rf.

Spec: beam-studio docs/prd/auto-full-area-preview-pose-check.md.

The wide-angle camera sits in the lid and the v4 calibration was shot with the lid at its open stop, so a frame
is only usable at that pose. The two chassis rims (the side rulers) run front to back along the bed's side edges.
`expected_rims` projects those edges through the calibration to get the curve each rim should follow in the raw
frame (straight under a pinhole model, bent under a fisheye one); `measure_rims` finds the rims on a frame with
Canny + probabilistic Hough and compares each segment against the curve's chord over the same rows.

That works on fhx2rf (pinhole), where the rims are rulers that stay straight. On fbb2 (fisheye) the bed edge has no
contrast on a bare honeycomb and the rims bend into pieces Hough misses, so `measure_ridges` instead scores the
thin LED highlight on the chassis edge along its projected curve (`RIM_OFFSET_MM` outside the bed edge).

Angle convention (shared with tools/lid_angle.py): degrees from vertical, positive when the lower end of the
segment is to the right of its upper end. At the open stop on fhx2rf the left rim reads about +2 and the
right rim about -2; a lowered lid moves both toward and past 0.
"""

import math

import cv2
import numpy as np

from fluxghost.utils.camera.calibration import project_points
from fluxghost.utils.camera.constants import L_PAD, T_PAD

ANALYSIS_WIDTH = 1280
CANNY = (50, 150)
HOUGH_THRESHOLD = 80
MIN_LINE_FRAC = 0.08  # a segment counts if longer than this fraction of the analysis width
MAX_LINE_GAP = 10
BAND_FRAC = 0.05  # a rim segment's midpoint must lie within this fraction of the width of the expected line
SEARCH_DEG = 10  # ... and within this many degrees of the expected angle
EDGE_STEP_MM = 10
DEFAULT_TOLERANCE_DEG = 1.5
# Fisheye (fbb2) only: the chassis edge the LEDs light up, relative to the bed's side edge, as (mm outward, mm along
# the calibration's z). Outward and z trade off along the line, so the pair was fitted on both sides at once.
# ponytail: fitted on one fbb2 (bare bed, 2026-11-17); check on a second unit before trusting it fleet-wide
RIM_OFFSET_MM = (10.0, -15.0)
RIDGE_SEARCH = 3  # px either side of the projected curve, full resolution
RIDGE_HALF = 15  # half-width of the background a highlight is measured against
RIDGE_MIN_ROWS = 50  # fewer in-frame rows than this scores 0
# Stronger side over 8 fbb2 runs (120 frames): >= 51.9 at the open stop, <= 14.1 lowered or shut, <= 12.0 mid-wobble
RIDGE_MIN = 30.0


def fit_line(points):
    """Least-squares x = a*y + b through (x, y) points: (angle from vertical in degrees, a, b)."""
    points = np.asarray(points, dtype=np.float64)
    a, b = np.polyfit(points[:, 1], points[:, 0], 1)
    return math.degrees(math.atan(a)), float(a), float(b)


def expected_rims(k, d, rvecs, tvecs, bed_w, bed_h, is_fisheye=True):
    """Expected rim lines in raw-frame pixels from the calibration.

    `rvecs` / `tvecs` are the per-region dicts `set_fisheye_height` computes; the left rim uses the `left`
    region, the right rim the `right` one. Returns {'left': {'deg', 'xs', 'ys'}, 'right': {...}}: the projected
    rim as points sorted by row, plus `deg`, a straight fit through them that is only reported when no rim is found.
    A fisheye projects the lit chassis edge `RIM_OFFSET_MM` outside the bed edge instead (see `measure_ridges`).
    """
    out = {}
    dx, z = RIM_OFFSET_MM if is_fisheye else (0.0, 0.0)
    for side, x in (('left', -dx), ('right', float(bed_w) + dx)):
        ys = np.arange(0.0, bed_h + EDGE_STEP_MM / 2, EDGE_STEP_MM)
        objp = np.stack([np.full_like(ys, x), ys, np.full_like(ys, z)], axis=1).reshape(-1, 1, 3).astype(np.float32)
        imgp = project_points(objp, rvecs[side], tvecs[side], k, d, is_fisheye=is_fisheye).reshape(-1, 2)
        if is_fisheye:
            # calibrate_fisheye_camera pads every frame before solving, so k and the extrinsics live in padded
            # coordinates; measure_rims works on the raw frame
            imgp = imgp - (L_PAD, T_PAD)
        imgp = imgp[np.argsort(imgp[:, 1])]
        out[side] = {'deg': fit_line(imgp)[0], 'xs': imgp[:, 0], 'ys': imgp[:, 1]}
    return out


def segments(gray):
    """Hough segments as (x1, y1, x2, y2, angle_deg) on the analysis-width image."""
    edges = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), *CANNY)
    min_len = int(gray.shape[1] * MIN_LINE_FRAC)
    lines = cv2.HoughLinesP(edges, 1, math.radians(1), HOUGH_THRESHOLD, minLineLength=min_len, maxLineGap=MAX_LINE_GAP)
    out = []
    for x1, y1, x2, y2 in lines[:, 0] if lines is not None else []:
        if y1 == y2:
            continue
        out.append((int(x1), int(y1), int(x2), int(y2), math.degrees(math.atan((x2 - x1) / (y2 - y1)))))
    return out


def measure_rims(frame, expected, tolerance_deg=DEFAULT_TOLERANCE_DEG):
    """Measure both rims on a raw BGR or gray frame against `expected_rims` output.

    Returns {'ok', 'left', 'right', 'expected_left', 'expected_right'}: measured angles are None when no
    segment lies near the expected curve; an expected angle is the curve's chord over the chosen segment (the
    one-line fit when there is none); `ok` needs both rims within `tolerance_deg` of their expected angle.
    """
    gray = frame if frame.ndim == 2 else cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    scale = ANALYSIS_WIDTH / w if w > ANALYSIS_WIDTH else 1.0
    if scale != 1.0:
        gray = cv2.resize(gray, (ANALYSIS_WIDTH, int(h * scale)), interpolation=cv2.INTER_AREA)
    segs = segments(gray)
    band = gray.shape[1] * BAND_FRAC
    result = {'ok': True}
    for side in ('left', 'right'):
        exp = expected[side]
        best = None
        for x1, y1, x2, y2, deg in segs:
            # The expected curve's chord over the segment's rows, in analysis pixels (a straight line under the
            # pinhole model this path serves). Rows beyond the projected bed clamp to its end points.
            ex1, ex2 = np.interp((y1 / scale, y2 / scale), exp['ys'], exp['xs']) * scale
            exp_deg = math.degrees(math.atan((ex2 - ex1) / (y2 - y1)))
            if abs((x1 + x2 - ex1 - ex2) / 2) > band or abs(deg - exp_deg) > SEARCH_DEG:
                continue
            # Longest segment wins: the ruler strip is the longest straight edge near the bed's side, while
            # honeycomb seams and tick marks nearby break into short pieces. Fitting through every candidate
            # instead let those pull the angle by several degrees on the study frames.
            length = math.hypot(x2 - x1, y2 - y1)
            if best is None or length > best[0]:
                best = (length, deg, exp_deg)
        measured = round(best[1], 1) if best else None
        exp_deg = best[2] if best else exp['deg']
        result[side] = measured
        result['expected_' + side] = round(exp_deg, 1)
        if measured is None or abs(best[1] - exp_deg) > tolerance_deg:
            result['ok'] = False
    return result


def ridge_score(gray, xs, ys):
    """Mean thin-highlight strength along the curve (xs, ys) on a full-resolution gray frame: per row, the brightest
    pixel within `RIDGE_SEARCH` of the curve minus the mean of the `2 * RIDGE_HALF + 1` pixels around it."""
    h, w = gray.shape
    rows = np.arange(max(math.ceil(ys[0]), 0), min(math.floor(ys[-1]), h - 1) + 1)
    cols = np.rint(np.interp(rows, ys, xs)).astype(int)
    margin = RIDGE_HALF + RIDGE_SEARCH
    keep = (cols >= margin) & (cols < w - margin)
    if keep.sum() < RIDGE_MIN_ROWS:
        return 0.0
    offsets = np.arange(-margin, margin + 1)
    win = gray[rows[keep, None], cols[keep, None] + offsets].astype(np.float32)
    k = 2 * RIDGE_HALF + 1
    csum = np.cumsum(np.pad(win, ((0, 0), (1, 0))), axis=1)
    means = (csum[:, k:] - csum[:, :-k]) / k  # centred on offsets -RIDGE_SEARCH .. RIDGE_SEARCH
    centres = win[:, RIDGE_HALF : RIDGE_HALF + 2 * RIDGE_SEARCH + 1]
    return float(np.clip(centres - means, 0, None).max(axis=1).mean())


def measure_ridges(frame, expected):
    """Fisheye pose check against `expected_rims` output: the LED highlight on the chassis edge must lie on its
    projected curve. Same result shape as `measure_rims`, with `left` / `right` the highlight scores and
    `expected_*` the `RIDGE_MIN` they are held to. One side is enough for `ok`: the highlight is specular and drops
    out on one side with the lid still at its stop, while a lowered lid moves both sides off their curves."""
    gray = frame if frame.ndim == 2 else cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    result = {'ok': False}
    for side in ('left', 'right'):
        score = ridge_score(gray, expected[side]['xs'], expected[side]['ys'])
        result[side] = round(score, 1)
        result['expected_' + side] = RIDGE_MIN
        result['ok'] = result['ok'] or score >= RIDGE_MIN
    return result
