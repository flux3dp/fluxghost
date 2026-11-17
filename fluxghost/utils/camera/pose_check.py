"""Camera pose check for the auto full-area preview on fbb2 / fhx2rf.

Spec: beam-studio docs/prd/auto-full-area-preview-pose-check.md.

The wide-angle camera sits in the lid and the v4 calibration was shot with the lid at its open stop, so a frame
is only usable at that pose. The two chassis rims (the side rulers) run front to back along the bed's side edges.
`expected_rims` projects those edges through the calibration to get the angle each rim should have in the raw
frame; `measure_rims` finds the rims on a frame with Canny + probabilistic Hough and compares.

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


def fit_line(points):
    """Least-squares x = a*y + b through (x, y) points: (angle from vertical in degrees, a, b)."""
    points = np.asarray(points, dtype=np.float64)
    a, b = np.polyfit(points[:, 1], points[:, 0], 1)
    return math.degrees(math.atan(a)), float(a), float(b)


def expected_rims(k, d, rvecs, tvecs, bed_w, bed_h, is_fisheye=True):
    """Expected rim lines in raw-frame pixels from the calibration.

    `rvecs` / `tvecs` are the per-region dicts `set_fisheye_height` computes; the left rim uses the `left`
    region, the right rim the `right` one. Returns {'left': {'deg', 'a', 'b'}, 'right': {...}}.
    """
    out = {}
    for side, x in (('left', 0.0), ('right', float(bed_w))):
        ys = np.arange(0.0, bed_h + EDGE_STEP_MM / 2, EDGE_STEP_MM)
        objp = np.stack([np.full_like(ys, x), ys, np.zeros_like(ys)], axis=1).reshape(-1, 1, 3).astype(np.float32)
        imgp = project_points(objp, rvecs[side], tvecs[side], k, d, is_fisheye=is_fisheye).reshape(-1, 2)
        if is_fisheye:
            # calibrate_fisheye_camera pads every frame before solving, so k and the extrinsics live in padded
            # coordinates; measure_rims works on the raw frame
            imgp = imgp - (L_PAD, T_PAD)
        deg, a, b = fit_line(imgp)
        out[side] = {'deg': deg, 'a': a, 'b': b}
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
    segment lies near the expected line; `ok` needs both rims within `tolerance_deg` of their expected angle.
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
            mid_x, mid_y = (x1 + x2) / 2, (y1 + y2) / 2
            # expected line in analysis pixels: x' = a*y' + b*scale
            if abs(mid_x - (exp['a'] * mid_y + exp['b'] * scale)) > band or abs(deg - exp['deg']) > SEARCH_DEG:
                continue
            # Longest segment wins: the ruler strip is the longest straight edge near the bed's side, while
            # honeycomb seams and tick marks nearby break into short pieces. Fitting through every candidate
            # instead let those pull the angle by several degrees on the study frames.
            length = math.hypot(x2 - x1, y2 - y1)
            if best is None or length > best[0]:
                best = (length, deg)
        measured = round(best[1], 1) if best else None
        result[side] = measured
        result['expected_' + side] = round(exp['deg'], 1)
        if measured is None or abs(measured - exp['deg']) > tolerance_deg:
            result['ok'] = False
    return result
