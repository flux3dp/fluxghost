"""Automatic solve-PnP: find the engraved calibration marks and tell which is which, with no pose prior.

The bed is a plane, so undistorted blob centres and bed coordinates are related by one homography. Each
hypothesis is one grid cell: blob a, its right neighbour b, its lower neighbour c and the blob closest to the
fourth corner. Four points give a homography, so strong perspective is right from the first step (a three-point
affine seed extrapolates onto wrong blobs and never recovers). The hypothesis then grows: map every blob onto
the bed, give each grid position its nearest blob, refit, repeat.

Only physical assumption: bed +x runs along image +x and bed +y along image +y (image not mirrored or rotated
by 90 degrees).
"""

import cv2
import numpy as np
from scipy.spatial import cKDTree

from .constants import L_PAD, T_PAD

# Where each value comes from (measurements, the cases seen on hardware): docs/api/camera-calibration.md,
# "auto_pnp constants".

# Blobs from different exposures closer than this (px) are the same mark
SAME_MARK_PX = 8
# A blob further than this (mm, on the bed) from every grid position is not a mark, while the fit is growing
ASSIGN_TOL_MM = 15.0
# ... and once the fit has settled. Drops a stray that sits near a missing mark
TIGHT_TOL_MM = 3.0
# Largest rms residual (mm) of the marks to one homography for a match to be accepted. It tracks how well k, d
# describe the camera. Suits the 16-mark lattice; callers with 8 marks pass a tighter one (see gate)
R_MAX_MM = 1.0
# Weak candidates (blobs down to this area, px) are only used within FILL_TOL_MM (mm) of a position predicted
# from the marks already matched, and only when at least FILL_MIN_FRACTION of the marks are there to predict from
WEAK_MIN_AREA = 4
FILL_TOL_MM = 2.0
FILL_MIN_FRACTION = 0.875
# How far perspective may stretch a cell's width / height ratio in the image before a seed is not worth trying
SEED_ASPECT = 2.5
# Nested-rectangle layouts only: how far the image scale along bed x may differ from the one along bed y in a
# finished match. A homography absorbs any stretch, so a pattern of other proportions fits without residual
MAX_ANISOTROPY = 1.25

NOT_ENOUGH_MARKS = 'NOT_ENOUGH_MARKS'
HIGH_RESIDUAL = 'HIGH_RESIDUAL'


PINHOLE_UNDISTORT_CRITERIA = (cv2.TERM_CRITERIA_COUNT | cv2.TERM_CRITERIA_EPS, 100, 1e-8)


def undistort_centers(raw_xy, k, d, is_fisheye=True):
    """Raw photo px -> the undistorted px space the rest of the calibration uses (P = k; padded for fisheye only,
    as get_remap_img is fed)."""
    pts = np.asarray(raw_xy, np.float64).reshape(-1, 1, 2)
    if not is_fisheye:
        # undistortPoints stops after 5 iterations: 0.5 px off at 85 % of the way to the corner with the fhx2rf
        # wide-angle k / d, where the manual flow finds its points on the exactly remapped photo
        return cv2.undistortPointsIter(pts, k, d, None, k, PINHOLE_UNDISTORT_CRITERIA).reshape(-1, 2)
    return cv2.fisheye.undistortPoints(pts + (L_PAD, T_PAD), k, d, np.eye(3), k).reshape(-1, 2)


def merge_exposures(blob_lists):
    """One list of [x, y, size, contrast] per exposure -> one list, each mark kept from its best-contrast exposure."""
    merged = []
    for blob in sorted((b for blobs in blob_lists for b in blobs), key=lambda b: -b[3]):
        if all(np.hypot(blob[0] - m[0], blob[1] - m[1]) > SAME_MARK_PX for m in merged):
            merged.append(blob)
    return merged


def _detector(min_area=15):
    # same parameters as find_blob_centers, dark blobs only
    p = cv2.SimpleBlobDetector_Params()
    p.minThreshold, p.maxThreshold = 10, 200
    p.filterByArea, p.minArea, p.maxArea = True, min_area, 1000
    p.filterByCircularity, p.minCircularity = True, 0.64
    p.filterByConvexity, p.minConvexity = True, 0.85
    p.filterByColor, p.blobColor = True, 0
    return cv2.SimpleBlobDetector_create(p)


def _contrast(gray, x, y, size):
    """Ring around the blob minus the blob, with the ring capped so a blown-out background does not win."""
    r = max(2, round(size / 2))
    x0, y0 = round(x), round(y)
    top, left = max(0, y0 - 3 * r), max(0, x0 - 3 * r)
    patch = gray[top : y0 + 3 * r + 1, left : x0 + 3 * r + 1]
    yy, xx = np.ogrid[top : top + patch.shape[0], left : left + patch.shape[1]]
    dist = np.hypot(xx - x0, yy - y0)
    return float(min(np.median(patch[(dist > 2 * r) & (dist <= 3 * r)]), 250) - patch[dist <= r].mean())


def detect_marks(img, k, d, min_area=15, is_fisheye=True):
    """auto_pnp_detect: dark blobs in a raw (still distorted, unpadded) BGR photo -> [[x, y, size, contrast]].

    Detection runs on the raw frame and only the centres are undistorted; x, y are in the same undistorted px
    space as solve_pnp_find_corners returns and solve_pnp_calculate takes.

    min_area=WEAK_MIN_AREA gives the weak candidates: hundreds per photo, mostly paper texture, usable only
    next to a position that is already predicted (see fill_missing).
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    keypoints = _detector(min_area).detect(gray)
    if not keypoints:
        return []
    und = undistort_centers([kp.pt for kp in keypoints], k, d, is_fisheye)
    return [
        [round(float(x), 2), round(float(y), 2), round(float(kp.size), 2), round(_contrast(gray, *kp.pt, kp.size), 1)]
        for (x, y), kp in zip(und, keypoints)
    ]


def _assign(model, und, bed, tol_mm):
    """Give each grid position its nearest blob within tol_mm on the bed, each blob used once."""
    on_bed = cv2.perspectiveTransform(und.reshape(-1, 1, 2), np.linalg.inv(model)).reshape(-1, 2)
    dist = np.linalg.norm(bed[:, None] - on_bed[None], axis=2)
    out = np.full(len(bed), -1)
    used = set()
    for g in np.argsort(dist.min(axis=1)):
        for b in np.argsort(dist[g]):
            if dist[g, b] > tol_mm:
                break
            if b not in used:
                out[g] = b
                used.add(b)
                break
    return out


def _upright(model, bed):
    """A grid can be similar to its own transpose (fbb2 wide-angle: 120/180/120 and 80/120/80 mm), and a
    homography fits the 90-degree-rotated assignment as well as the true one."""
    c = bed.mean(axis=0)
    q = cv2.perspectiveTransform(np.array([c, c + (1, 0), c + (0, 1)]).reshape(-1, 1, 2), model).reshape(-1, 2)
    ex, ey = q[1] - q[0], q[2] - q[0]
    return ex[0] > abs(ex[1]) and ey[1] > abs(ey[0])


def _isotropic(model, bed):
    """Whether a millimetre along bed x and one along bed y are about as long in the image (MAX_ANISOTROPY)."""
    c = bed.mean(axis=0)
    q = cv2.perspectiveTransform(np.array([c, c + (1, 0), c + (0, 1)]).reshape(-1, 1, 2), model).reshape(-1, 2)
    ratio = np.linalg.norm(q[1] - q[0]) / np.linalg.norm(q[2] - q[0])
    return 1 / MAX_ANISOTROPY <= ratio <= MAX_ANISOTROPY


def _usable(model):
    return model is not None and abs(np.linalg.det(model)) > 1e-9


def _residuals(model, und, bed):
    return cv2.perspectiveTransform(und.reshape(-1, 1, 2), np.linalg.inv(model)).reshape(-1, 2) - bed


def match_grid(und, bed, neighbours=16, iterations=6, r_max=R_MAX_MM):
    """Assign blobs to grid positions.

    :param und: undistorted blob centres, px
    :param bed: mark positions in bed mm, in any order: a full rectangular lattice, or nested rectangles
    :param r_max: residual (mm) under which a hypothesis with every mark ends the search. Must be the limit the
        caller gates with: a complete but poorer fit (a stray in a mark's place) would otherwise end the search
        before the right one is tried
    :return: (blob index per grid position or -1, rms residual to the homography in mm), (None, inf) if no fit
    """
    und = np.asarray(und, np.float64).reshape(-1, 2)
    bed = np.asarray(bed, np.float64).reshape(-1, 2)
    xs, ys = np.unique(bed[:, 0]), np.unique(bed[:, 1])
    pos = {tuple(p): i for i, p in enumerate(bed)}
    # a cell is a mark with the next mark to its right, the next one below, and the mark closing the rectangle.
    # On a full lattice these are the lattice cells; on two nested rectangles (the 8-mark layouts) the two rectangles.
    cells, ratios = [], []
    for x, y in pos:
        right = [v for v in xs if v > x and (v, y) in pos]
        below = [v for v in ys if v > y and (x, v) in pos]
        if right and below and (right[0], below[0]) in pos:
            cells.append((pos[(x, y)], pos[(right[0], y)], pos[(x, below[0])], pos[(right[0], below[0])]))
            ratios.append((right[0] - x) / (below[0] - y))
    if not cells:
        return None, np.inf
    nested = len(bed) < len(xs) * len(ys)
    if nested:
        # a cell's corners are not each other's nearest marks here, so a seed may be any blobs
        neighbours = len(und)
    best = (-1, np.inf, None)
    tree = cKDTree(und)
    centre = bed.mean(axis=0).reshape(1, 1, 2)
    enough = max(4, len(bed) // 3)
    near_needed = enough
    if nested:
        # the seed's own four blobs always pass the check below: ask for half of the other marks as well
        near_needed = 4 + (len(bed) - 4) // 2
    seen = set()  # assignments already refined; many seeds land on the same one
    # a cell's width / height on the bed; perspective changes it in the image, but not by more than SEED_ASPECT
    min_ratio, max_ratio = min(ratios) / SEED_ASPECT, max(ratios) * SEED_ASPECT
    # ponytail: every plausible (blob, right, lower) seed times every cell, in Python. Instant when all marks are
    # there (early return), seconds when marks are missing. Vectorise the assignment or rank seeds by blob size
    # if that failure path must be faster.
    for a in range(len(und)):
        near = np.argsort(np.linalg.norm(und - und[a], axis=1))[1 : neighbours + 1]
        for b in near:
            ab = und[b] - und[a]
            if ab[0] <= abs(ab[1]):  # right neighbour: mostly along image +x, as _upright requires of the result
                continue
            for c in near:
                ac = und[c] - und[a]
                if c == b or ac[1] <= abs(ac[0]):
                    continue
                if not min_ratio <= np.linalg.norm(ab) / np.linalg.norm(ac) <= max_ratio:
                    continue
                dists = np.linalg.norm(und - (und[b] + und[c] - und[a]), axis=1)
                dists[[a, b, c]] = np.inf
                e = int(np.argmin(dists))
                # the fourth corner must sit near where the parallelogram puts it
                if dists[e] > 0.5 * min(np.linalg.norm(ab), np.linalg.norm(ac)):
                    continue
                img = und[[a, b, c, e]].astype(np.float32)
                for cell in cells:
                    model = cv2.getPerspectiveTransform(bed[list(cell)].astype(np.float32), img)
                    if not _usable(model) or not _upright(model, bed):
                        continue
                    # cheap rejection before the assignment loop: a seed that is not a real cell puts the grid
                    # where there are no blobs. Radius = ASSIGN_TOL_MM at the grid centre's scale, doubled
                    # because one cell extrapolates badly.
                    step = cv2.perspectiveTransform(np.hstack([centre, centre + (ASSIGN_TOL_MM, 0)]), model)[0]
                    radius = 2 * np.linalg.norm(step[1] - step[0])
                    grid_img = cv2.perspectiveTransform(bed.reshape(-1, 1, 2), model).reshape(-1, 2)
                    if np.isfinite(tree.query(grid_img, distance_upper_bound=radius)[0]).sum() < near_needed:
                        continue
                    assign = None
                    # grow at the loose tolerance (one cell extrapolates badly), then settle at the tight one,
                    # so hypotheses are ranked by marks that really fit and not by strays swept in on the way
                    for tol in (ASSIGN_TOL_MM, TIGHT_TOL_MM):
                        if tol == TIGHT_TOL_MM:
                            # a stray swept in at the loose tolerance drags a least-squares fit: start the tight
                            # stage from the fit most marks agree on
                            ok = assign >= 0
                            robust, _ = cv2.findHomography(und[assign[ok]], bed[ok], cv2.RANSAC, TIGHT_TOL_MM)
                            if _usable(robust):
                                model = np.linalg.inv(robust)
                        assign = None
                        for it in range(iterations):
                            new = _assign(model, und, bed, tol)
                            if tol == ASSIGN_TOL_MM and it == 0:
                                # refinement is deterministic from here, so the same start gives the same end
                                if new.tobytes() in seen:
                                    assign = None
                                    break
                                seen.add(new.tobytes())
                            ok = new >= 0
                            stable = assign is not None and np.array_equal(new, assign)
                            assign = new
                            if ok.sum() < enough or stable:
                                break
                            model, _ = cv2.findHomography(bed[ok], und[assign[ok]], 0)
                            if not _usable(model):
                                break
                        if assign is None or not _usable(model) or (assign >= 0).sum() < enough:
                            break
                    if assign is None or not _usable(model):
                        continue
                    ok = assign >= 0
                    # only the finished fit is checked for proportions: one cell alone extrapolates too badly
                    if ok.sum() < 4 or not _upright(model, bed) or (nested and not _isotropic(model, bed)):
                        continue
                    rms = float(np.sqrt((_residuals(model, und[assign[ok]], bed[ok]) ** 2).sum(axis=1).mean()))
                    if ok.sum() > best[0] or (ok.sum() == best[0] and rms < best[1]):
                        best = (int(ok.sum()), rms, assign.copy())
                        # every mark, fitting well: no other hypothesis can beat it by enough to matter
                        if best[0] == len(bed) and rms <= r_max:
                            return best[2], best[1]
    return best[2], best[1]


def fill_missing(assign, und, bed, weak):
    """Look for the marks the detector missed among the weak candidates, next to where the others say they are.

    Returns (und with the filled centres appended, assign, number filled).
    """
    assign = assign.copy()
    ok = assign >= 0
    weak = np.asarray(weak, np.float64).reshape(-1, 2)
    if ok.all() or ok.sum() < FILL_MIN_FRACTION * len(bed) or not len(weak):
        return und, assign, 0
    model, _ = cv2.findHomography(bed[ok], und[assign[ok]], 0)
    on_bed = cv2.perspectiveTransform(weak.reshape(-1, 1, 2), np.linalg.inv(model)).reshape(-1, 2)
    filled = []
    for g in np.flatnonzero(~ok):
        near = np.linalg.norm(on_bed - bed[g], axis=1) <= FILL_TOL_MM
        if near.any():
            # one mark seen in several exposures gives several candidates; the median ignores a lone speck
            assign[g] = len(und) + len(filled)
            filled.append(np.median(weak[near], axis=0))
    return (np.vstack([und, *filled]) if filled else und), assign, len(filled)


def gate(matched, total, rms, r_max=R_MAX_MM):
    """Decide whether a match may be used for solve-PnP.

    :param int matched: grid positions that got a blob
    :param int total: grid positions
    :param float rms: residual of the matched marks to one homography, mm (inf when nothing fitted)
    :param float r_max: residual limit, mm. The default suits the 16-mark lattice; with 8 marks a homography
        absorbs most of one wrong mark, so those callers pass a tighter one
    :return: None to accept, or NOT_ENOUGH_MARKS / HIGH_RESIDUAL
    """
    if matched < total:
        return NOT_ENOUGH_MARKS
    if rms > r_max:
        return HIGH_RESIDUAL
    return None


def match_marks(blob_lists, ref_points, weak_lists=None, r_max=None):
    """auto_pnp_match: blobs per exposure ([x, y, size, contrast], undistorted px) -> one image point per ref point.

    :return: dict with points (per ref point, [x, y] or None), matched, filled, rms, and reason (None when accepted)
    """
    bed = np.asarray(ref_points, np.float64).reshape(-1, 2)
    blobs = merge_exposures(blob_lists)
    und = np.array([b[:2] for b in blobs], np.float64).reshape(-1, 2)
    r_max = R_MAX_MM if r_max is None else r_max
    assign, rms = match_grid(und, bed, r_max=r_max) if len(und) >= 4 else (None, np.inf)
    if assign is None:
        assign = np.full(len(bed), -1)
    weak = [b[:2] for blobs in weak_lists or [] for b in blobs]
    und, assign, filled = fill_missing(assign, und, bed, weak)
    if filled:
        ok = assign >= 0
        model, _ = cv2.findHomography(bed[ok], und[assign[ok]], 0)
        rms = float(np.sqrt((_residuals(model, und[assign[ok]], bed[ok]) ** 2).sum(axis=1).mean()))
    matched = int((assign >= 0).sum())
    return {
        'points': [und[i].tolist() if i >= 0 else None for i in assign],
        'matched': matched,
        'filled': filled,
        'rms': None if np.isinf(rms) else rms,
        'reason': gate(matched, len(bed), rms, r_max),
    }
