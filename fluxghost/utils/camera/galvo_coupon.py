"""Galvo field-lens calibration coupon solver (HEXA G, `solve_galvo_coupon`).

Port of the factory `correction.html` solve method ("解算方法"), driven by
Beam Studio's galvo calibration flow (beam-studio docs/prd/hexa-ii-galvo/
hexa-g-galvo-calibration.md §7.8 / §7.9).

Input: a bed-coordinate image (mm, nominal `px_per_mm`, +Y down) of a dark
sheet carrying two kinds of marks:

- the galvo coupon: 9x9 node rings with cross arms, 12 discovery X marks,
  8 validation rings, one small identity ring (command coordinates relative
  to the galvo field centre C);
- the nozzle-cut L frame: 8 L marks with vertices on the square C +- half
  (corners and edge midpoints), the ruler.

Pipeline, in the factory's order and with its "do not" list honoured:

1. separate the two kinds of marks (green channel for galvo marks; a
   sequence of brightness thresholds for the L frame, first one whose ruler
   passes the self-check wins);
2. ruler: L components -> two line fits per L -> intersection (groove
   geometric centre, not intensity centroid) -> 3x3 nominal bins -> least
   squares px = A*mm + b with one-at-a-time outlier rejection, self-check
   (span within 2% of the 197.99 mm diagonal, RMS < 0.5 mm);
3. node centres: rings by radial distribution (not hole filling), lattice
   from pairwise vectors grouped by direction (not length), orientation
   from the identity ring, per-node ellipse fit;
4. affine fit p = L c + t, L = R U (QR) -> scale_x, scale_y, skew;
5. validation rings: affine-only and affine + bilinear residual prediction;
6. field centre: galvo origin in the L-frame (nozzle) coordinate system.

Everything in mm is in the L-frame coordinate system unless stated: the full
A^-1 mapping is used (not just the two per-axis px/mm), so the frame's own
rotation on the image is removed before the QR step and reported separately
as `rotation_deg`.
"""

import math

import cv2
import numpy as np

DEFAULT_DISCOVERY = [
    [49.5, 49.5],
    [-49.5, 49.5],
    [49.5, -49.5],
    [-49.5, -49.5],
    [5.5, 49.5],
    [-5.5, 49.5],
    [5.5, -49.5],
    [-5.5, -49.5],
    [49.5, 5.5],
    [49.5, -5.5],
    [-49.5, 5.5],
    [-49.5, -5.5],
]
DEFAULT_VALIDATION = [
    [5.5, 5.5],
    [-5.5, 5.5],
    [5.5, -5.5],
    [-5.5, -5.5],
    [27.5, 27.5],
    [-27.5, 27.5],
    [27.5, -27.5],
    [-27.5, -27.5],
]
# factory defaults (flatbed scanner) first; the last three are for the head camera's
# stitched photograph, whose L grooves sit only 30-60 above a background that itself
# varies by that much from tile to tile under the machine's lighting: a third element
# names a top-hat kernel (mm) that subtracts the local background before the threshold.
DEFAULT_THRESHOLDS = {
    'galvo_green': 150,
    'l_frame': [
        [200, 'any'],
        [160, 'red'],
        [120, 'red'],
        [100, 'any'],
        [60, 'any'],
        [40, 'any', 2.0],
        [28, 'any', 2.0],
        [18, 'any', 2.0],
    ],
}
L_DIAGONAL_MM = 197.99  # 140 * sqrt(2), corner to opposite corner
RULER_SPAN_TOLERANCE = 0.02
RULER_RESIDUAL_MM = 0.5
RULER_MIN_VERTICES = 6
L_COMPONENT_MM = (6.5, 11.0)  # factory: usable L components are 6.5-11 mm wide
# An L whose corner did not cut, or whose arms a burn blob split, is two arm components:
# each this long, at most this thick, and paired when their lines meet within L_PAIR_GAP_MM
# of the near end of both and the far ends sit an arm's length away.
L_ARM_MM = (4.5, 11.0)
L_ARM_THICK_MM = 3.0
L_PAIR_GAP_MM = 2.5
L_PAIR_FAR_MM = (5.0, 11.5)
# Guided detection (photographs): the L is looked for where the layout puts it, as two
# straight arms in a thin-line response that does not care whether the groove photographs
# bright or dark. Only the middle of each arm is used, clear of the corner (which may not
# have cut) and of the stroke's end (where the beam dwelt and burnt a blob).
GUIDED_KERNELS_MM = [1.0, 1.5, 2.0]
GUIDED_SEARCH_MM = 6.0
GUIDED_ARM_SPAN_MM = (2.0, 6.5)
GUIDED_BAND_MM = 1.0
GUIDED_MIN_SNR = 3.0
# locate: px/mm candidates tried around the estimate from the coupon's extent
LOCATE_PPM_STEPS = [0.80 + 0.04 * i for i in range(11)]


class SolveError(Exception):
    """A stage could not produce a trustworthy result; `info` is the client-facing code."""

    def __init__(self, info, reason):
        super().__init__(info, reason)
        self.info = info
        self.reason = reason


def _as_float_pairs(value):
    return [[float(p[0]), float(p[1])] for p in value]


def parse_params(params, image_shape):
    """Fill in the PRD §7.8 defaults so the solver and the renderer agree on the pattern."""
    h, w = image_shape[:2]
    thresholds = dict(DEFAULT_THRESHOLDS)
    thresholds.update(params.get('thresholds') or {})
    l_frame = {'half': 70.0, 'arm': 8.0}
    l_frame.update(params.get('l_frame') or {})
    arm = params.get('arm') or [2.0, 4.5]
    invert = params.get('invert') or [True, True]
    return {
        'px_per_mm': float(params.get('px_per_mm', 20)),
        'pitch': float(params.get('pitch', 11)),
        'grid': int(params.get('grid', 9)),
        'node_r': float(params.get('node_r', 1.25)),
        'arm': [float(arm[0]), float(arm[1])],
        'discovery': _as_float_pairs(params.get('discovery') or DEFAULT_DISCOVERY),
        'validation': _as_float_pairs(params.get('validation') or DEFAULT_VALIDATION),
        'identity': [float(v) for v in (params.get('identity') or [-44, -51])],
        'identity_r': float(params.get('identity_r', 0.5)),
        'l_frame': {'half': float(l_frame['half']), 'arm': float(l_frame['arm'])},
        'expected_center_px': [float(v) for v in (params.get('expected_center_px') or [w / 2.0, h / 2.0])],
        'invert': [bool(invert[0]), bool(invert[1])],
        'thresholds': thresholds,
        'annotate': bool(params.get('annotate', False)),
        # 'affine' (a stitched or scanned image), 'projective' (a hand-held photograph of the
        # flat sheet), or 'auto': affine unless its self-check fails and 8 vertices allow more
        'ruler_model': str(params.get('ruler_model', 'affine')),
        # the guided (layout-driven) L detection runs before the threshold masks; off, only
        # the masks run, as on the factory's scans
        'guided': bool(params.get('guided', True)),
        # find the coupon in the image first; expected_center_px and px_per_mm are then only
        # a starting point and may be far off (a photograph of unknown scale)
        'locate': bool(params.get('locate', False)),
    }


# ---------------------------------------------------------------------------
# geometry helpers


def _fit_line(xs, ys):
    """Total-least-squares line through binary pixels: (point, unit direction)."""
    pts = np.column_stack([xs, ys]).astype(np.float64)
    mean = pts.mean(axis=0)
    centred = pts - mean
    _, _, vt = np.linalg.svd(centred, full_matrices=False)
    return mean, vt[0]


def _intersect(p1, d1, p2, d2):
    mat = np.column_stack([d1, -d2])
    det = np.linalg.det(mat)
    if abs(det) < 1e-9:
        return None
    s = np.linalg.solve(mat, p2 - p1)[0]
    return p1 + s * d1


def _point_line_distance(pts, p, d):
    rel = pts - p
    return np.abs(rel[:, 0] * d[1] - rel[:, 1] * d[0])


def _fit_circle(xs, ys):
    """Algebraic (Kasa) circle fit: centre (x, y), radius. None if degenerate."""
    x = xs.astype(np.float64)
    y = ys.astype(np.float64)
    a = np.column_stack([x, y, np.ones_like(x)])
    rhs = x * x + y * y
    try:
        sol, _, rank, _ = np.linalg.lstsq(a, rhs, rcond=None)
    except np.linalg.LinAlgError:
        return None
    if rank < 3:
        return None
    cx, cy = sol[0] / 2, sol[1] / 2
    r2 = sol[2] + cx * cx + cy * cy
    if r2 <= 0:
        return None
    return np.array([cx, cy]), math.sqrt(r2)


def _angular_coverage(xs, ys, centre, bins=36):
    ang = np.arctan2(ys - centre[1], xs - centre[0])
    hist, _ = np.histogram(ang, bins=bins, range=(-math.pi, math.pi))
    return float(np.count_nonzero(hist)) / bins


# ---------------------------------------------------------------------------
# step 1: masks


def _channel(img, mode):
    b, g, r = img[:, :, 0], img[:, :, 1], img[:, :, 2]
    if mode == 'red':
        return r
    if mode == 'green':
        return g
    if mode == 'blue':
        return b
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def _chebyshev_roi(shape, centre, inner_px, outer_px):
    """Boolean mask of pixels whose max(|dx|, |dy|) from `centre` lies in [inner, outer)."""
    h, w = shape[:2]
    ys = np.abs(np.arange(h, dtype=np.float32) - centre[1])[:, None]
    xs = np.abs(np.arange(w, dtype=np.float32) - centre[0])[None, :]
    cheb = np.maximum(ys, xs)
    return (cheb >= inner_px) & (cheb < outer_px)


# ---------------------------------------------------------------------------
# step 2: ruler


def _fit_l_vertex(xs, ys, ppm):
    """Vertex of one L component from two arm line fits (groove geometric centre).

    Returns (vertex xy, mean perpendicular residual px) or None.
    """
    pts = np.column_stack([xs, ys]).astype(np.float64)
    x0, y0, x1, y1 = xs.min(), ys.min(), xs.max(), ys.max()
    corners = np.array([[x0, y0], [x1, y0], [x0, y1], [x1, y1]], dtype=np.float64)
    near = 1.5 * ppm
    counts = [np.count_nonzero(np.max(np.abs(pts - c), axis=1) < near) for c in corners]
    pivot = corners[int(np.argmax(counts))]
    rel = pts - pivot
    far = np.max(np.abs(rel), axis=1) > 1.0 * ppm  # drop the vertex blob itself
    horizontal = np.abs(rel[:, 0]) > np.abs(rel[:, 1])
    sel_a = far & horizontal
    sel_b = far & ~horizontal
    if np.count_nonzero(sel_a) < 10 or np.count_nonzero(sel_b) < 10:
        return None
    pa, da = _fit_line(pts[sel_a, 0], pts[sel_a, 1])
    pb, db = _fit_line(pts[sel_b, 0], pts[sel_b, 1])
    vertex = _intersect(pa, da, pb, db)
    if vertex is None:
        return None
    # refine: reassign every pixel to the nearer line, excluding the vertex blob
    for _ in range(2):
        dist_a = _point_line_distance(pts, pa, da)
        dist_b = _point_line_distance(pts, pb, db)
        far = np.linalg.norm(pts - vertex, axis=1) > 1.0 * ppm
        sel_a = far & (dist_a < dist_b)
        sel_b = far & (dist_b <= dist_a)
        if np.count_nonzero(sel_a) < 10 or np.count_nonzero(sel_b) < 10:
            return None
        pa, da = _fit_line(pts[sel_a, 0], pts[sel_a, 1])
        pb, db = _fit_line(pts[sel_b, 0], pts[sel_b, 1])
        new_vertex = _intersect(pa, da, pb, db)
        if new_vertex is None:
            return None
        vertex = new_vertex
    # arms must be roughly perpendicular, otherwise this is not an L
    if abs(float(np.dot(da, db))) > 0.5:
        return None
    residual = float(
        np.mean(np.concatenate([_point_line_distance(pts[sel_a], pa, da), _point_line_distance(pts[sel_b], pb, db)]))
    )
    return vertex, residual


def _fit_arm(xs, ys):
    """One straight arm: (point, unit direction, end a, end b, mean residual px)."""
    p, d = _fit_line(xs, ys)
    pts = np.column_stack([xs, ys]).astype(np.float64)
    t = (pts - p) @ d
    residual = float(np.mean(_point_line_distance(pts, p, d)))
    return p, d, p + d * t.min(), p + d * t.max(), residual


def _pair_arms(arms, ppm):
    """Vertices from pairs of perpendicular arms that meet at one end of each."""
    found = []
    for i in range(len(arms)):
        for j in range(i + 1, len(arms)):
            a, b = arms[i], arms[j]
            if abs(float(np.dot(a[1], b[1]))) > 0.5:
                continue
            vertex = _intersect(a[0], a[1], b[0], b[1])
            if vertex is None:
                continue
            ok = True
            for arm in (a, b):
                ends = [np.linalg.norm(vertex - arm[2]) / ppm, np.linalg.norm(vertex - arm[3]) / ppm]
                if min(ends) > L_PAIR_GAP_MM or not (L_PAIR_FAR_MM[0] <= max(ends) <= L_PAIR_FAR_MM[1]):
                    ok = False
            if ok:
                found.append((vertex, (a[4] + b[4]) / 2))
    return found


def find_l_vertices(mask, ppm):
    """All plausible L vertices (px) in a binary mask: list of (vertex, residual).

    An L that is one component is fitted whole. One whose corner is missing, or that a
    burn blob at a stroke end has split, shows up as two arm-sized components; those
    are fitted as lines and paired. Both kinds may report the same L; solve_ruler keeps
    the one nearer its nominal place.
    """
    lo, hi = L_COMPONENT_MM[0] * ppm, L_COMPONENT_MM[1] * ppm
    arm_lo, arm_hi, arm_thick = L_ARM_MM[0] * ppm, L_ARM_MM[1] * ppm, L_ARM_THICK_MM * ppm
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    found = []
    arms = []
    for i in range(1, count):
        x, y, w, h, area = stats[i]
        whole = lo <= w <= hi and lo <= h <= hi
        arm = arm_lo <= max(w, h) <= arm_hi and min(w, h) <= arm_thick
        if not (whole or arm):
            continue
        if area < 2 * L_COMPONENT_MM[0] * ppm * 0.1 * ppm:  # thinner than 0.1 mm strokes: noise
            continue
        sub = labels[y : y + h, x : x + w] == i
        ys, xs = np.nonzero(sub)
        if whole:
            fit = _fit_l_vertex(xs + x, ys + y, ppm)
            if fit is not None:
                found.append(fit)
                continue
        if arm:
            arms.append(_fit_arm(xs + x, ys + y))
    return found + _pair_arms(arms, ppm)


def l_frame_layout(half, arm):
    """The 8 Ls as (vertex mm, x-arm end mm, y-arm end mm), the nozzle's layout (beam-studio
    galvoCoupon.ts buildLFrameMarks): corners point inward, edge midpoints along their axis to +."""
    out = []
    for vx, vy in [
        (-half, -half),
        (0, -half),
        (half, -half),
        (half, 0),
        (half, half),
        (0, half),
        (-half, half),
        (-half, 0),
    ]:
        xa = arm if vx == 0 else -np.sign(vx) * arm
        ya = arm if vy == 0 else -np.sign(vy) * arm
        out.append(
            (np.array([vx, vy], np.float64), np.array([vx + xa, vy], np.float64), np.array([vx, vy + ya], np.float64))
        )
    return out


def thin_line_response(gray, k_mm, ppm):
    """What is thinner than k_mm and stands out of its surroundings, bright or dark: a cut
    slit photographs as a dark line, a bright line, or one of each wall, with the light."""
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (int(k_mm * ppm) | 1,) * 2)
    return cv2.add(cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, kernel), cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT, kernel))


def _guided_arm(response, start_px, end_px, ppm):
    """Line through one arm, looked for between start_px and end_px (the part of the arm to
    use) and GUIDED_SEARCH_MM either side of it: the peak of the response's profile across
    the arm, then a weighted line through the response within GUIDED_BAND_MM of the peak.
    Returns (point, direction, residual px, snr) or None."""
    along_x = abs(end_px[0] - start_px[0]) > abs(end_px[1] - start_px[1])
    search = GUIDED_SEARCH_MM * ppm
    if along_x:
        x0, x1 = sorted([start_px[0], end_px[0]])
        y0, y1 = start_px[1] - search, start_px[1] + search
    else:
        y0, y1 = sorted([start_px[1], end_px[1]])
        x0, x1 = start_px[0] - search, start_px[0] + search
    x0, x1, y0, y1 = [round(v) for v in (x0, x1, y0, y1)]
    # the part of the arm must be in the image; the search across it may be cut by the edge
    along_in = (x0 >= 0 and x1 <= response.shape[1]) if along_x else (y0 >= 0 and y1 <= response.shape[0])
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(response.shape[1], x1), min(response.shape[0], y1)
    across = (y1 - y0) if along_x else (x1 - x0)
    if not along_in or across < 2 * GUIDED_BAND_MM * ppm or x1 - x0 < 3 or y1 - y0 < 3:
        return None
    win = response[y0:y1, x0:x1].astype(np.float32)
    profile = win.sum(axis=1 if along_x else 0)
    profile = np.convolve(profile, np.ones(3) / 3.0, mode='same')
    peak = int(np.argmax(profile))
    snr = float(profile[peak] / max(float(np.median(profile)), 1e-6))
    if snr < GUIDED_MIN_SNR:
        return None
    band = int(GUIDED_BAND_MM * ppm)
    if along_x:
        rows = np.arange(max(0, peak - band), min(win.shape[0], peak + band + 1))
        sub = win[rows, :]
        weight = sub.sum(axis=0)
        centre = (sub * rows[:, None]).sum(axis=0) / np.maximum(weight, 1e-6)
        keep = weight > 0.2 * weight.max()
        pts = np.column_stack([np.arange(win.shape[1])[keep] + x0, centre[keep] + y0])
    else:
        cols = np.arange(max(0, peak - band), min(win.shape[1], peak + band + 1))
        sub = win[:, cols]
        weight = sub.sum(axis=1)
        centre = (sub * cols[None, :]).sum(axis=1) / np.maximum(weight, 1e-6)
        keep = weight > 0.2 * weight.max()
        pts = np.column_stack([centre[keep] + x0, np.arange(win.shape[0])[keep] + y0])
    if len(pts) < 10:
        return None
    point, direction = _fit_line(pts[:, 0], pts[:, 1])
    residual = float(np.mean(_point_line_distance(pts, point, direction)))
    return point, direction, residual, snr


def find_l_vertices_guided(gray, ppm, centre_px, half, arm, k_mm):
    """L vertices from where the layout says the Ls are: list of (vertex px, residual px).

    When the expected centre is a few mm off, the Ls it finds say by how much: with at least
    three found and some missing, the search is repeated once from the corrected centre.
    """
    response = thin_line_response(gray, k_mm, ppm)
    layout = l_frame_layout(half, arm)
    found = _guided_pass(response, ppm, centre_px, layout, arm)
    hits = [i for i, (point, _) in enumerate(found) if point is not None]
    if 3 <= len(hits) < len(layout):
        shift = np.median(np.array([found[i][0] - (centre_px + layout[i][0] * ppm) for i in hits]), axis=0)
        again = _guided_pass(response, ppm, centre_px + shift, layout, arm)
        if sum(point is not None for point, _ in again) > len(hits):
            found = again
    return [f for f in found if f[0] is not None]


def _guided_pass(response, ppm, centre_px, layout, arm):
    """One pass over the layout; an L not found is (None, None) so the caller can pair up."""
    lo, hi = GUIDED_ARM_SPAN_MM
    found = []
    for vertex_mm, x_end_mm, y_end_mm in layout:
        nominal = centre_px + vertex_mm * ppm
        vertex = nominal
        fit = None
        # Twice: the first pass measures the arms from where the layout says the vertex is,
        # which may be millimetres off, so the sampled span can reach into the corner and the
        # other arm; the second samples each arm from the vertex just found.
        for _ in range(2):
            arms = []
            for end_mm in (x_end_mm, y_end_mm):
                unit = (end_mm - vertex_mm) / arm
                one = _guided_arm(response, vertex + unit * lo * ppm, vertex + unit * hi * ppm, ppm)
                if one is None:
                    break
                arms.append(one)
            if len(arms) < 2:
                fit = None
                break
            (pa, da, ra, _), (pb, db, rb, _) = arms
            if abs(float(np.dot(da, db))) > 0.5:
                fit = None
                break
            point = _intersect(pa, da, pb, db)
            if point is None or np.linalg.norm(point - nominal) > GUIDED_SEARCH_MM * ppm:
                fit = None
                break
            vertex = point
            fit = (point, (ra + rb) / 2)
        found.append(fit if fit is not None else (None, None))
    return found


def _fit_ruler(vertices_px, nominal_mm):
    """Least squares px = A*mm + b. Returns (A, b, residual_mm (N,2))."""
    design = np.column_stack([nominal_mm, np.ones(len(nominal_mm))])
    sol, _, _, _ = np.linalg.lstsq(design, vertices_px, rcond=None)
    a_mat = sol[:2].T  # 2x2, px per mm
    b_vec = sol[2]
    pred = nominal_mm @ a_mat.T + b_vec
    res_px = vertices_px - pred
    res_mm = res_px @ np.linalg.inv(a_mat).T
    return a_mat, b_vec, res_mm


def _fit_ruler_projective(vertices_px, nominal_mm):
    """Least squares homography mm -> px. Returns (H, residual_mm (N,2))."""
    h_mat, _ = cv2.findHomography(nominal_mm.astype(np.float64), vertices_px.astype(np.float64), 0)
    if h_mat is None:
        raise SolveError('RULER_INVALID', 'projective ruler is degenerate')
    back = cv2.perspectiveTransform(vertices_px.reshape(-1, 1, 2).astype(np.float64), np.linalg.inv(h_mat)).reshape(
        -1, 2
    )
    return h_mat, back - nominal_mm


def _affine_at_origin(h_mat):
    """The homography's local affine (A, b) at mm = 0: what px/mm means for a projective ruler."""
    w = h_mat[2, 2]
    b_vec = h_mat[:2, 2] / w
    a_mat = (h_mat[:2, :2] - np.outer(b_vec, h_mat[2, :2])) / w
    return a_mat, b_vec


def solve_ruler(vertices, centre_px, ppm_nominal, half, model='affine'):
    """Bin L vertices into the 3x3 nominal grid and fit the ruler; raises SolveError.

    `model`: 'affine' (px = A mm + b) or 'projective' (a homography, for a hand-held
    photograph of the flat sheet). The self-check is the same for both.
    """
    if len(vertices) < RULER_MIN_VERTICES:
        raise SolveError('RULER_INVALID', 'only %d L vertices found, need %d' % (len(vertices), RULER_MIN_VERTICES))
    bins = {}
    for vertex, residual in vertices:
        rel = (np.asarray(vertex) - centre_px) / ppm_nominal
        key = (int(np.clip(round(rel[0] / half), -1, 1)), int(np.clip(round(rel[1] / half), -1, 1)))
        if key == (0, 0):
            continue
        nominal = np.array([key[0] * half, key[1] * half])
        off = float(np.linalg.norm(rel - nominal))
        if key not in bins or off < bins[key][1]:
            bins[key] = (np.asarray(vertex, dtype=np.float64), off, residual)
    keys = sorted(bins)
    px = np.array([bins[k][0] for k in keys])
    mm = np.array([[k[0] * half, k[1] * half] for k in keys], dtype=np.float64)
    rejected = []
    h_mat = None
    while True:
        if len(keys) < RULER_MIN_VERTICES:
            raise SolveError(
                'RULER_INVALID', 'fewer than %d vertices left after outlier rejection' % RULER_MIN_VERTICES
            )
        if model == 'projective':
            h_mat, res_mm = _fit_ruler_projective(px, mm)
            a_mat, b_vec = _affine_at_origin(h_mat)
        else:
            a_mat, b_vec, res_mm = _fit_ruler(px, mm)
        norms = np.linalg.norm(res_mm, axis=1)
        worst = int(np.argmax(norms))
        if norms[worst] <= RULER_RESIDUAL_MM or len(keys) <= RULER_MIN_VERTICES:
            break
        rejected.append((keys[worst], px[worst]))
        keys.pop(worst)
        px = np.delete(px, worst, axis=0)
        mm = np.delete(mm, worst, axis=0)
    rms = float(math.sqrt(np.mean(norms**2)))
    measured_mm = mm + res_mm
    diffs = measured_mm[:, None, :] - measured_mm[None, :, :]
    span = float(np.max(np.linalg.norm(diffs, axis=2)))
    if abs(span - L_DIAGONAL_MM) > RULER_SPAN_TOLERANCE * L_DIAGONAL_MM:
        raise SolveError('RULER_INVALID', 'vertex span %.2f mm is not within 2%% of %.2f mm' % (span, L_DIAGONAL_MM))
    if rms >= RULER_RESIDUAL_MM:
        raise SolveError('RULER_INVALID', 'ruler fit RMS %.3f mm >= %.1f mm' % (rms, RULER_RESIDUAL_MM))
    return {
        'A': a_mat,
        'b': b_vec,
        'H': h_mat,
        'model': model,
        'px_per_mm_x': float(np.linalg.norm(a_mat[:, 0])),
        'px_per_mm_y': float(np.linalg.norm(a_mat[:, 1])),
        'vertices_used': len(keys),
        'rms_mm': rms,
        'span_mm': span,
        'used': [(k, p) for k, p in zip(keys, px)],
        'rejected': rejected,
    }


# ---------------------------------------------------------------------------
# step 3: node centres


def _ring_candidates(mask, px_to_mm, inner_half_mm, node_r, identity_r):
    """Split galvo-mask components into node-size rings and identity-size blobs.

    Returns (rings [{px, mm, r_mm}], small [{px, mm}]). Everything else (cross
    arms, X arms, debris) is dropped by bbox size, radial spread or coverage.
    """
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    rings, small = [], []
    ring_d = 2 * node_r
    for i in range(1, count):
        x, y, w, h, area = stats[i]
        centre_px = np.array([x + w / 2.0, y + h / 2.0])
        centre_mm = px_to_mm(centre_px)
        if np.max(np.abs(centre_mm)) > inner_half_mm:
            continue
        # bbox in mm (frame scale is close to isotropic; use the mean px/mm)
        w_mm, h_mm = w * px_to_mm.mm_per_px, h * px_to_mm.mm_per_px
        side = max(w_mm, h_mm)
        if 1.5 * identity_r <= side <= 2.0 * (identity_r + 0.5) and min(w_mm, h_mm) >= 0.6 * side:
            if area / float(w * h) >= 0.45:
                small.append({'px': centre_px, 'mm': centre_mm})
            continue
        if not (0.7 * ring_d <= side <= 1.4 * ring_d and min(w_mm, h_mm) >= 0.5 * ring_d):
            continue
        sub = labels[y : y + h, x : x + w] == i
        ys, xs = np.nonzero(sub)
        xs = xs + x
        ys = ys + y
        fit = _fit_circle(xs, ys)
        if fit is None:
            continue
        centre, radius = fit
        radius_mm = radius * px_to_mm.mm_per_px
        if not (0.75 * node_r <= radius_mm <= 1.3 * node_r):
            continue
        radii = np.hypot(xs - centre[0], ys - centre[1])
        if np.std(radii) / radius > 0.25:  # not a ring: radial distribution too broad
            continue
        if _angular_coverage(xs, ys, centre) < 0.5:
            continue
        rings.append({'px': centre, 'mm': px_to_mm(centre), 'r_mm': radius_mm})
    return rings, small


def _direction_peak(angles, weights, exclude=None, bins=180):
    hist, edges = np.histogram(angles, bins=bins, range=(0, math.pi), weights=weights)
    # circular smoothing over +-2 bins
    kernel = np.ones(5) / 5.0
    padded = np.concatenate([hist[-2:], hist, hist[:2]])
    smooth = np.convolve(padded, kernel, mode='valid')
    if exclude is not None:
        centres = (edges[:-1] + edges[1:]) / 2
        d = np.abs(((centres - exclude) + math.pi / 2) % math.pi - math.pi / 2)
        smooth[d < math.radians(25)] = 0
    idx = int(np.argmax(smooth))
    if smooth[idx] <= 0:
        return None
    return (edges[idx] + edges[idx + 1]) / 2


def _axis_from_vectors(vectors, peak):
    ang = np.arctan2(vectors[:, 1], vectors[:, 0]) % math.pi
    d = np.abs(((ang - peak) + math.pi / 2) % math.pi - math.pi / 2)
    sel = vectors[d < math.radians(10)]
    if len(sel) == 0:
        return None
    ref = np.array([math.cos(peak), math.sin(peak)])
    sel = np.where((sel @ ref)[:, None] < 0, -sel, sel)
    lengths = np.linalg.norm(sel, axis=1)
    median = np.median(lengths)
    sel = sel[np.abs(lengths - median) < 0.15 * median]
    if len(sel) == 0:
        return None
    return sel.mean(axis=0)


def build_lattice(points_mm, pitch, grid):
    """Lattice axes (u, v) in mm and integer indices for the points on the lattice.

    Pairwise vectors of lattice length are grouped by direction, not by length
    (the factory warning: with unequal axis scales a length window also admits
    the half-diagonal validation rings).
    """
    pts = np.asarray(points_mm, dtype=np.float64)
    n = len(pts)
    if n < 6:
        raise SolveError('GRID_INVALID', 'only %d ring candidates found' % n)
    diffs = pts[None, :, :] - pts[:, None, :]
    lengths = np.linalg.norm(diffs, axis=2)
    sel = (lengths > 0.75 * pitch) & (lengths < 1.3 * pitch)
    iu = np.triu_indices(n, 1)
    sel = sel[iu]
    vectors = diffs[iu][sel]
    if len(vectors) < 4:
        raise SolveError('GRID_INVALID', 'not enough neighbour vectors to build a lattice')
    angles = np.arctan2(vectors[:, 1], vectors[:, 0]) % math.pi
    weights = np.ones(len(vectors))
    peak_u = _direction_peak(angles, weights)
    peak_v = _direction_peak(angles, weights, exclude=peak_u) if peak_u is not None else None
    if peak_u is None or peak_v is None:
        raise SolveError('GRID_INVALID', 'could not find two lattice directions')
    u = _axis_from_vectors(vectors, peak_u)
    v = _axis_from_vectors(vectors, peak_v)
    if u is None or v is None:
        raise SolveError('GRID_INVALID', 'could not estimate lattice axes')
    basis = np.column_stack([u, v])
    if abs(np.linalg.det(basis)) < 0.3 * pitch * pitch:
        raise SolveError('GRID_INVALID', 'lattice axes are degenerate')
    inv = np.linalg.inv(basis)
    # the origin with the most on-lattice candidates is a node, not a validation ring
    best = None
    for k in range(n):
        coords = (pts - pts[k]) @ inv.T
        frac = np.max(np.abs(coords - np.round(coords)), axis=1)
        on = frac < 0.2
        if best is None or np.count_nonzero(on) > best[0]:
            best = (int(np.count_nonzero(on)), k, on, np.round(coords).astype(int))
    _, _, on, idx = best
    idx = idx[on]
    members = np.nonzero(on)[0]
    # densest grid x grid window
    best_win = None
    for i0 in range(idx[:, 0].min(), idx[:, 0].max() - grid + 2):
        for j0 in range(idx[:, 1].min(), idx[:, 1].max() - grid + 2):
            inside = (idx[:, 0] >= i0) & (idx[:, 0] < i0 + grid) & (idx[:, 1] >= j0) & (idx[:, 1] < j0 + grid)
            c = int(np.count_nonzero(inside))
            if best_win is None or c > best_win[0]:
                best_win = (c, i0, j0, inside)
    _, i0, j0, inside = best_win
    idx = idx[inside] - np.array([i0, j0])
    members = members[inside]
    # refine axes and origin by least squares over the member points
    design = np.column_stack([idx, np.ones(len(idx))]).astype(np.float64)
    sol, _, _, _ = np.linalg.lstsq(design, pts[members], rcond=None)
    u, v, origin = sol[0], sol[1], sol[2]
    return {'u': u, 'v': v, 'origin': origin, 'members': members, 'index': idx}


def _orientation_from_identity(lattice, small_mm, pitch, grid, identity_offset_mm):
    """Which corner is (-44,-44) and which lattice axis is Y, from the identity ring."""
    u, v, origin = lattice['u'], lattice['v'], lattice['origin']
    last = grid - 1
    best = None
    for ic in (0, last):
        for jc in (0, last):
            corner = origin + ic * u + jc * v
            for axis_name, axis, idx in (('u', u, ic), ('v', v, jc)):
                outward = -axis if idx == 0 else axis
                predicted = corner + (identity_offset_mm / pitch) * outward
                for s in small_mm:
                    d = float(np.linalg.norm(s - predicted))
                    if best is None or d < best[0]:
                        best = (d, ic, jc, axis_name, predicted)
    if best is None or best[0] > 2.0:
        return None
    _, ic, jc, y_axis, predicted = best
    return {'ic': ic, 'jc': jc, 'y_axis': y_axis, 'identity_mm': predicted, 'distance_mm': best[0]}


def _orientation_from_invert(lattice, grid, invert):
    """Fallback orientation: lattice axis closest to image x is X; signs from the invert flags.

    Assumption (to be confirmed on the first real coupon): with Beam Studio's
    CO2 default `invert = [true, true]` the coupon prints with command +X along
    image +x and +Y along image +y; a flag that differs mirrors that axis.
    """
    u, v = lattice['u'], lattice['v']
    last = grid - 1
    if abs(u[0]) >= abs(v[0]):
        x_axis, y_axis = 'u', 'v'
        xa, ya = u, v
    else:
        x_axis, y_axis = 'v', 'u'
        xa, ya = v, u
    sign_x = 1.0 if invert[0] else -1.0
    sign_y = 1.0 if invert[1] else -1.0
    ic = 0 if xa[0] * sign_x > 0 else last
    jc = 0 if ya[1] * sign_y > 0 else last
    if x_axis == 'u':
        return {'ic': ic, 'jc': jc, 'y_axis': y_axis}
    return {'ic': jc, 'jc': ic, 'y_axis': y_axis}


def _index_to_command(i, j, orientation, pitch, grid):
    """Lattice indices (i along u, j along v) -> command mm."""
    last = grid - 1
    half = last * pitch / 2.0
    if orientation['y_axis'] == 'v':
        xi, ci, yj, cj = i, orientation['ic'], j, orientation['jc']
    else:
        xi, ci, yj, cj = j, orientation['jc'], i, orientation['ic']
    x = pitch * xi - half if ci == 0 else half - pitch * xi
    y = pitch * yj - half if cj == 0 else half - pitch * yj
    return np.array([x, y])


def fit_ring_centre(mask, predicted_px, ppm, node_r, min_fraction=0.35):
    """Ellipse (conic) fit of the ring pixels around `predicted_px`; None if too few pixels.

    Unequal axis scales turn the commanded circle into an ellipse and a
    partial ring's centroid is biased, hence the conic fit on all stroke
    pixels (both groove walls), whose centre is the groove centre line's.
    """
    radius = 0.5 * (node_r + 2.0) * ppm  # inside the arms (start at r = 2.0 mm)
    radius = max(radius, (node_r + 0.6) * ppm)
    x0 = int(max(0, math.floor(predicted_px[0] - radius)))
    y0 = int(max(0, math.floor(predicted_px[1] - radius)))
    x1 = int(min(mask.shape[1], math.ceil(predicted_px[0] + radius) + 1))
    y1 = int(min(mask.shape[0], math.ceil(predicted_px[1] + radius) + 1))
    if x1 <= x0 or y1 <= y0:
        return None
    sub = mask[y0:y1, x0:x1]
    ys, xs = np.nonzero(sub)
    xs = xs + x0
    ys = ys + y0
    d = np.hypot(xs - predicted_px[0], ys - predicted_px[1])
    keep = (d < radius) & (d > 0.4 * node_r * ppm)
    xs, ys = xs[keep], ys[keep]
    expected = 2 * math.pi * node_r * 0.3 * ppm * ppm  # a 0.3 mm stroke's worth of pixels
    if len(xs) < max(20, min_fraction * expected):
        return None
    pts = np.column_stack([xs, ys]).astype(np.float32).reshape(-1, 1, 2)
    try:
        (cx, cy), (w, h), _ = cv2.fitEllipseDirect(pts)
    except cv2.error:
        return None
    if not (np.isfinite(cx) and np.isfinite(cy)):
        return None
    semi = np.array([w, h]) / 2.0 / ppm
    if not (0.7 * node_r <= semi.min() and semi.max() <= 1.4 * node_r):
        fit = _fit_circle(xs, ys)
        if fit is None:
            return None
        return fit[0]
    return np.array([cx, cy])


# ---------------------------------------------------------------------------
# step 4: affine


def fit_affine(cmd, meas):
    """Least squares meas = L cmd + t. Returns (L, t)."""
    design = np.column_stack([cmd, np.ones(len(cmd))])
    sol, _, _, _ = np.linalg.lstsq(design, meas, rcond=None)
    return sol[:2].T, sol[2]


def decompose_affine(l_mat):
    """L = R U with R a rotation (det +1) and U upper triangular, positive diagonal.

    A reflection (det L < 0) is reported as mirrored and removed by flipping
    the command Y axis before the decomposition.
    """
    mirrored = bool(np.linalg.det(l_mat) < 0)
    work = l_mat @ np.diag([1.0, -1.0]) if mirrored else l_mat
    q, r = np.linalg.qr(work)
    signs = np.sign(np.diag(r))
    signs[signs == 0] = 1
    q = q @ np.diag(signs)
    r = np.diag(signs) @ r
    rotation = math.degrees(math.atan2(q[1, 0], q[0, 0]))
    return {
        'R': q,
        'U': r,
        'scale_x': float(r[0, 0]),
        'scale_y': float(math.hypot(r[0, 1], r[1, 1])),
        'skew_deg': float(math.degrees(math.atan2(r[0, 1], r[1, 1]))),
        'rotation_deg': float(rotation),
        'mirrored': mirrored,
    }


def _rms_max(vectors):
    if len(vectors) == 0:
        return None, None
    norms = np.linalg.norm(np.asarray(vectors), axis=1)
    return float(math.sqrt(np.mean(norms**2))), float(norms.max())


# ---------------------------------------------------------------------------
# driver


class _PxToMm:
    """Callable px -> L-frame mm from the ruler fit; `mm_per_px` is the mean scale."""

    def __init__(self, a_mat, b_vec):
        self.inv = np.linalg.inv(a_mat)
        self.b = b_vec
        self.a = a_mat
        self.mm_per_px = 2.0 / (np.linalg.norm(a_mat[:, 0]) + np.linalg.norm(a_mat[:, 1]))

    def __call__(self, px):
        return (np.asarray(px, dtype=np.float64) - self.b) @ self.inv.T

    def to_px(self, mm):
        return np.asarray(mm, dtype=np.float64) @ self.a.T + self.b

    def grid_mm(self, xs, ys):
        """mm_x, mm_y rasters for pixel column coordinates xs (1,W) and rows ys (H,1)."""
        dx, dy = xs - self.b[0], ys - self.b[1]
        return self.inv[0, 0] * dx + self.inv[0, 1] * dy, self.inv[1, 0] * dx + self.inv[1, 1] * dy


class _PxToMmProjective(_PxToMm):
    """The same through a homography; `mm_per_px`, `a`, `b` are its local affine at the origin."""

    def __init__(self, h_mat):
        a_mat, b_vec = _affine_at_origin(h_mat)
        super().__init__(a_mat, b_vec)
        self.h = h_mat
        self.h_inv = np.linalg.inv(h_mat)

    def __call__(self, px):
        pts = np.asarray(px, dtype=np.float64).reshape(-1, 1, 2)
        out = cv2.perspectiveTransform(pts, self.h_inv).reshape(-1, 2)
        return out[0] if np.asarray(px).ndim == 1 else out

    def to_px(self, mm):
        pts = np.asarray(mm, dtype=np.float64).reshape(-1, 1, 2)
        out = cv2.perspectiveTransform(pts, self.h).reshape(-1, 2)
        return out[0] if np.asarray(mm).ndim == 1 else out

    def grid_mm(self, xs, ys):
        h = self.h_inv
        w = h[2, 0] * xs + h[2, 1] * ys + h[2, 2]
        return (h[0, 0] * xs + h[0, 1] * ys + h[0, 2]) / w, (h[1, 0] * xs + h[1, 1] * ys + h[1, 2]) / w


def _px_to_mm_for(ruler):
    return _PxToMmProjective(ruler['H']) if ruler.get('H') is not None else _PxToMm(ruler['A'], ruler['b'])


def locate_coupon(galvo_raw, gray, pitch, half, arm):
    """Where the coupon is and at what scale, from the node rings and then the L frame.

    The node rings are the near-square galvo components a ring's share full (about 0.4;
    an X stroke's box is emptier, an arm's box is a line): their median is the coupon's
    centre and the median distance between nearest rings is one pitch, at the galvo's
    own scale, so a first guess at px/mm. That guess is swept over LOCATE_PPM_STEPS with
    the guided L detection and the sweep's best (most vertices, then least residual)
    wins. Returns (centre_px, ppm) or None when there are no rings to go by.
    """
    count, labels, stats, centroids = cv2.connectedComponentsWithStats(galvo_raw.astype(np.uint8), connectivity=8)
    limit = 0.05 * max(galvo_raw.shape)
    rings = []
    for i in range(1, count):
        x, y, w, h, area = stats[i]
        if area < 8 or max(w, h) >= limit or min(w, h) < 3:
            continue
        if not (0.7 <= w / float(h) <= 1.4) or not (0.25 <= area / float(w * h) <= 0.6):
            continue
        # a ring encloses background: a hole that does not touch its box's border. An X
        # stroke or a broken arm fills a box of the same shape and share without one.
        hole = (labels[y : y + h, x : x + w] != i).astype(np.uint8)
        n_bg, bg = cv2.connectedComponents(hole, connectivity=4)
        border = np.unique(np.concatenate([bg[0, :], bg[-1, :], bg[:, 0], bg[:, -1]]))
        if len(set(range(1, n_bg)) - set(border.tolist())) == 0:
            continue
        rings.append(centroids[i])
    if len(rings) < 12:
        return None
    pts = np.array(rings)
    centre = np.median(pts, axis=0)
    diffs = np.linalg.norm(pts[:, None, :] - pts[None, :, :], axis=2)
    np.fill_diagonal(diffs, np.inf)
    nearest = np.sort(diffs.min(axis=1))
    ppm0 = float(np.median(nearest)) / pitch
    if ppm0 <= 0:
        return None
    best = None
    for step in LOCATE_PPM_STEPS:
        ppm = ppm0 * step
        vertices = find_l_vertices_guided(gray, ppm, centre, half, arm, 1.5)
        if not vertices:
            continue
        score = (len(vertices), -float(np.mean([r for _, r in vertices])))
        if best is None or score > best[0]:
            best = (score, ppm)
    return (centre, best[1] if best is not None else ppm0)


def solve_galvo_coupon(img, params):
    """Solve one coupon image (BGR uint8). Returns (result dict, annotated BGR or None).

    Raises SolveError for RULER_INVALID / GRID_INVALID.
    """
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    p = parse_params(params, img.shape)
    ppm_nominal = p['px_per_mm']
    centre = np.array(p['expected_center_px'])
    half, arm_len = p['l_frame']['half'], p['l_frame']['arm']
    thresholds = p['thresholds']

    # --- 1. masks
    is_gray = bool(np.array_equal(img[:, :, 0], img[:, :, 1]) and np.array_equal(img[:, :, 1], img[:, :, 2]))
    galvo_raw = img[:, :, 1] > int(thresholds['galvo_green'])
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    located = None
    if p['locate']:
        located = locate_coupon(galvo_raw, gray, p['pitch'], half, arm_len)
        if located is not None:
            centre, ppm_nominal = located
    kernel = np.ones((3, 3), np.uint8)
    galvo_dilated = cv2.dilate(galvo_raw.astype(np.uint8), kernel, iterations=max(1, int(0.3 * ppm_nominal)))

    def ruler_models():
        if p['ruler_model'] == 'auto':
            return ['affine', 'projective']
        return [p['ruler_model']]

    def solve_ruler_at(roi_centre):
        errors = []
        # guided first: the layout says where each L is, and the thin-line response does not
        # care whether the groove photographs bright or dark
        for k_mm in GUIDED_KERNELS_MM if p['guided'] else []:
            vertices = find_l_vertices_guided(gray, ppm_nominal, roi_centre, half, arm_len, k_mm)
            for model in ruler_models():
                try:
                    found = solve_ruler(vertices, roi_centre, ppm_nominal, half, model)
                except SolveError as e:
                    errors.append('guided %g/%s: %s' % (k_mm, model, e.reason))
                    continue
                found['threshold'] = ['guided', k_mm]
                found['vertices_found'] = len(vertices)
                return found
        # then the factory's masks: the L frame lives in a ring around the coupon, vertices at
        # +-half, arms `arm_len` inward
        ring_roi = _chebyshev_roi(img.shape, roi_centre, (half - arm_len - 3) * ppm_nominal, (half + 12) * ppm_nominal)
        for entry in thresholds['l_frame']:
            threshold, mode = entry[0], entry[1]
            tophat_mm = float(entry[2]) if len(entry) > 2 else 0.0
            channel = _channel(img, mode)
            if tophat_mm > 0:
                # what stands out of its surroundings within tophat_mm: the groove, not
                # the tile-to-tile lighting nor a burn smear wider than the kernel
                kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (int(tophat_mm * ppm_nominal) | 1,) * 2)
                channel = cv2.morphologyEx(channel, cv2.MORPH_TOPHAT, kernel)
            mask = (channel > int(threshold)) & ring_roi
            if mode != 'any' and not is_gray:
                mask &= galvo_dilated == 0  # "non-galvo marks" (meaningless on a grayscale image)
            vertices = find_l_vertices(mask, ppm_nominal)
            for model in ruler_models():
                try:
                    found = solve_ruler(vertices, roi_centre, ppm_nominal, half, model)
                except SolveError as e:
                    errors.append(
                        '%s/%s%s/%s: %s'
                        % (threshold, mode, '/tophat%g' % tophat_mm if tophat_mm else '', model, e.reason)
                    )
                    continue
                found['threshold'] = list(entry)
                found['vertices_found'] = len(vertices)
                return found
        raise SolveError('RULER_INVALID', '; '.join(errors) or 'no L-frame threshold set given')

    ruler = solve_ruler_at(centre)
    if ruler['vertices_used'] < 8 and np.linalg.norm(ruler['b'] - centre) > 2 * ppm_nominal:
        # expected_center_px was off: the ring ROI clipped some Ls. Retry around the
        # ruler's own origin (the nozzle's C) and keep whichever used more vertices.
        try:
            retry = solve_ruler_at(ruler['b'])
            if retry['vertices_used'] > ruler['vertices_used']:
                ruler = retry
        except SolveError:
            pass

    px_to_mm = _px_to_mm_for(ruler)
    ppm_mean = 1.0 / px_to_mm.mm_per_px

    # --- 3. galvo mask + ring candidates
    # Everything inside Chebyshev radius (half - arm - 1) of the ruler origin is galvo
    # territory: the coupon reaches ~53.4 mm, the nearest L arm tip is at half - arm.
    inner_mm = half - arm_len - 1
    ys = np.arange(img.shape[0], dtype=np.float32)[:, None]
    xs = np.arange(img.shape[1], dtype=np.float32)[None, :]
    mm_x, mm_y = px_to_mm.grid_mm(xs, ys)
    inner_roi = (np.abs(mm_x) < inner_mm) & (np.abs(mm_y) < inner_mm)
    del mm_x, mm_y
    galvo_mask = galvo_raw & inner_roi
    rings, small = _ring_candidates(galvo_mask, px_to_mm, inner_mm, p['node_r'], p['identity_r'])
    ring_mm = np.array([r['mm'] for r in rings]) if rings else np.zeros((0, 2))
    lattice = build_lattice(ring_mm, p['pitch'], p['grid'])

    identity_offset = abs(p['identity'][1] - (-(p['grid'] - 1) * p['pitch'] / 2.0))
    orientation = _orientation_from_identity(lattice, [s['mm'] for s in small], p['pitch'], p['grid'], identity_offset)
    if orientation is not None:
        orientation['source'] = 'identity'
    else:
        orientation = _orientation_from_invert(lattice, p['grid'], p['invert'])
        orientation['source'] = 'invert'
    prior = _orientation_from_invert(lattice, p['grid'], p['invert'])
    orientation['matches_invert'] = bool(
        prior['ic'] == orientation['ic']
        and prior['jc'] == orientation['jc']
        and prior['y_axis'] == orientation['y_axis']
    )

    # --- per-node ellipse fit at the lattice-predicted position
    grid = p['grid']
    found_index = {tuple(ij): m for ij, m in zip(lattice['index'], lattice['members'])}
    node_cmd, node_mm, node_px, missing_px = [], [], [], []
    for i in range(grid):
        for j in range(grid):
            if (i, j) in found_index:
                predicted_mm = rings[found_index[(i, j)]]['mm']
            else:
                predicted_mm = lattice['origin'] + i * lattice['u'] + j * lattice['v']
            predicted_px = px_to_mm.to_px(predicted_mm)
            fitted = fit_ring_centre(galvo_mask, predicted_px, ppm_mean, p['node_r'])
            if fitted is None:
                missing_px.append(predicted_px)
                continue
            node_cmd.append(_index_to_command(i, j, orientation, p['pitch'], grid))
            node_mm.append(px_to_mm(fitted))
            node_px.append(fitted)
    nodes_found = len(node_cmd)
    if nodes_found < 6:
        raise SolveError('GRID_INVALID', 'only %d of %d nodes measured' % (nodes_found, grid * grid))
    node_cmd = np.array(node_cmd)
    node_mm = np.array(node_mm)

    # --- 4. affine
    l_mat, t_vec = fit_affine(node_cmd, node_mm)
    dec = decompose_affine(l_mat)
    l_inv = np.linalg.inv(l_mat)
    affine_res = (node_mm - node_cmd @ l_mat.T - t_vec) @ l_inv.T
    raw_res = (node_mm - t_vec) @ dec['R'] - node_cmd  # R^T (p - t) - c
    affine_rms, affine_max = _rms_max(affine_res)
    raw_rms, raw_max = _rms_max(raw_res)

    # --- 5. validation rings
    residual_by_cmd = {(round(c[0], 3), round(c[1], 3)): r for c, r in zip(node_cmd, affine_res)}
    val_affine, val_bilinear, val_px = [], [], []
    half_grid = (grid - 1) * p['pitch'] / 2.0
    for vx, vy in p['validation']:
        c = np.array([vx, vy])
        predicted_mm = l_mat @ c + t_vec
        measured = fit_ring_centre(galvo_mask, px_to_mm.to_px(predicted_mm), ppm_mean, p['node_r'])
        if measured is None:
            continue
        measured_mm = px_to_mm(measured)
        val_px.append(measured)
        err_affine = l_inv @ (measured_mm - predicted_mm)
        val_affine.append(err_affine)
        # bilinear interpolation of the affine residuals of the enclosing cell
        fx, fy = (vx + half_grid) / p['pitch'], (vy + half_grid) / p['pitch']
        i0, j0 = math.floor(fx), math.floor(fy)
        wx, wy = fx - i0, fy - j0
        total, acc = 0.0, np.zeros(2)
        for di, dj, wgt in ((0, 0, (1 - wx) * (1 - wy)), (1, 0, wx * (1 - wy)), (0, 1, (1 - wx) * wy), (1, 1, wx * wy)):
            key = (round(-half_grid + (i0 + di) * p['pitch'], 3), round(-half_grid + (j0 + dj) * p['pitch'], 3))
            if key in residual_by_cmd and wgt > 0:
                acc += wgt * residual_by_cmd[key]
                total += wgt
        interp = acc / total if total > 0 else np.zeros(2)
        val_bilinear.append(err_affine - interp)
    va_rms, va_max = _rms_max(val_affine)
    vb_rms, vb_max = _rms_max(val_bilinear)

    result = {
        'ruler': {
            'px_per_mm_x': ruler['px_per_mm_x'],
            'px_per_mm_y': ruler['px_per_mm_y'],
            'vertices_used': ruler['vertices_used'],
            'vertices_found': ruler['vertices_found'],
            'rms_mm': ruler['rms_mm'],
            'span_mm': ruler['span_mm'],
            'threshold': ruler['threshold'],
            'model': ruler['model'],
        },
        'located': None
        if located is None
        else {'center_px': [float(located[0][0]), float(located[0][1])], 'px_per_mm': float(located[1])},
        'nodes_found': nodes_found,
        'scale_x': dec['scale_x'],
        'scale_y': dec['scale_y'],
        'skew_deg': dec['skew_deg'],
        'rotation_deg': dec['rotation_deg'],
        'mirrored': dec['mirrored'],
        'affine_rms': affine_rms,
        'affine_max': affine_max,
        'raw_rms': raw_rms,
        'raw_max': raw_max,
        'validation_affine': None if va_rms is None else {'rms': va_rms, 'max': va_max, 'count': len(val_affine)},
        'validation_bilinear': None if vb_rms is None else {'rms': vb_rms, 'max': vb_max, 'count': len(val_bilinear)},
        'field_center_mm': [float(t_vec[0]), float(t_vec[1])],
        'orientation': {
            'source': orientation['source'],
            'matches_invert': orientation['matches_invert'],
            'identity_distance_mm': orientation.get('distance_mm'),
        },
    }
    annotated = None
    if p['annotate']:
        annotated = _annotate(
            img, ruler, node_px, affine_res, missing_px, val_px, px_to_mm, orientation, t_vec, ppm_mean
        )
    return result, annotated


def _annotate(img, ruler, node_px, affine_res, missing_px, val_px, px_to_mm, orientation, t_vec, ppm):
    out = img.copy()
    r = max(2, int(0.6 * ppm))
    for key, px in ruler['used']:
        c = (round(px[0]), round(px[1]))
        cv2.circle(out, c, 2 * r, (0, 255, 0), 2)
        cv2.putText(out, '%d,%d' % key, (c[0] + 2 * r, c[1]), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 1)
    for _, px in ruler['rejected']:
        c = (round(px[0]), round(px[1]))
        cv2.circle(out, c, 2 * r, (0, 0, 255), 2)
    for px, res in zip(node_px, affine_res):
        c = (round(px[0]), round(px[1]))
        cv2.circle(out, c, r, (255, 255, 0), 1)
        tip = px + res * 20 * ppm  # residual vectors x20
        cv2.line(out, c, (round(tip[0]), round(tip[1])), (0, 255, 255), 1)
    for px in missing_px:
        c = (round(px[0]), round(px[1]))
        cv2.drawMarker(out, c, (255, 0, 255), cv2.MARKER_TILTED_CROSS, 2 * r, 2)
    for px in val_px:
        c = (round(px[0]), round(px[1]))
        cv2.circle(out, c, r, (255, 128, 0), 1)
    if orientation.get('identity_mm') is not None:
        px = px_to_mm.to_px(orientation['identity_mm'])
        cv2.circle(out, (round(px[0]), round(px[1])), r, (0, 165, 255), 2)
    fc = px_to_mm.to_px(t_vec)
    cv2.drawMarker(out, (round(fc[0]), round(fc[1])), (255, 255, 255), cv2.MARKER_CROSS, 4 * r, 2)
    return out
