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

from .constants import L_PAD, T_PAD

# Blobs from different exposures closer than this (px) are the same mark
SAME_MARK_PX = 8
# A blob further than this (mm, on the bed) from every grid position is not a mark
ASSIGN_TOL_MM = 15.0
# Every mark is required: each region pose is solved from exactly its four marks. The residual to one homography
# also tracks how well k, d describe this camera: with all marks matched it was 0.46 to 0.71 mm on the units
# measured, and the worst preview error inside the mark grid is about the same figure. 0.75 is deliberately tight,
# to see how many units it turns away (their way out is a new ChArUco calibration); a stray taking a mark's place
# gives 3 mm or more.
R_MAX_MM = 0.75

NOT_ENOUGH_MARKS = 'NOT_ENOUGH_MARKS'
HIGH_RESIDUAL = 'HIGH_RESIDUAL'


def undistort_centers(raw_xy, k, d):
    """Raw photo px -> the undistorted px space the rest of the calibration uses (padded, P = k)."""
    pts = (np.asarray(raw_xy, np.float64) + (L_PAD, T_PAD)).reshape(-1, 1, 2)
    return cv2.fisheye.undistortPoints(pts, k, d, np.eye(3), k).reshape(-1, 2)


def merge_exposures(blob_lists):
    """One list of [x, y, size, contrast] per exposure -> one list, each mark kept from its best-contrast exposure."""
    merged = []
    for blob in sorted((b for blobs in blob_lists for b in blobs), key=lambda b: -b[3]):
        if all(np.hypot(blob[0] - m[0], blob[1] - m[1]) > SAME_MARK_PX for m in merged):
            merged.append(blob)
    return merged


def _detector():
    # same parameters as find_blob_centers, dark blobs only
    p = cv2.SimpleBlobDetector_Params()
    p.minThreshold, p.maxThreshold = 10, 200
    p.filterByArea, p.minArea, p.maxArea = True, 15, 1000
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


def detect_marks(img, k, d):
    """auto_pnp_detect: dark blobs in a raw (still distorted, unpadded) BGR photo -> [[x, y, size, contrast]].

    Detection runs on the raw frame and only the centres are undistorted; x, y are in the same undistorted px
    space as solve_pnp_find_corners returns and solve_pnp_calculate takes.
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    keypoints = _detector().detect(gray)
    if not keypoints:
        return []
    und = undistort_centers([kp.pt for kp in keypoints], k, d)
    return [
        [float(x), float(y), float(kp.size), _contrast(gray, kp.pt[0], kp.pt[1], kp.size)]
        for (x, y), kp in zip(und, keypoints)
    ]


def _assign(model, und, bed):
    """Give each grid position its nearest blob within ASSIGN_TOL_MM on the bed, each blob used once."""
    on_bed = cv2.perspectiveTransform(und.reshape(-1, 1, 2), np.linalg.inv(model)).reshape(-1, 2)
    dist = np.linalg.norm(bed[:, None] - on_bed[None], axis=2)
    out = np.full(len(bed), -1)
    used = set()
    for g in np.argsort(dist.min(axis=1)):
        for b in np.argsort(dist[g]):
            if dist[g, b] > ASSIGN_TOL_MM:
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


def _usable(model):
    return model is not None and abs(np.linalg.det(model)) > 1e-9


def _residuals(model, und, bed):
    return cv2.perspectiveTransform(und.reshape(-1, 1, 2), np.linalg.inv(model)).reshape(-1, 2) - bed


def match_grid(und, bed, neighbours=8, iterations=6):
    """Assign blobs to grid positions.

    :param und: undistorted blob centres, px
    :param bed: grid positions in bed mm, a full rectangular lattice in any order
    :return: (blob index per grid position or -1, rms residual to the homography in mm), (None, inf) if no fit
    """
    und = np.asarray(und, np.float64).reshape(-1, 2)
    bed = np.asarray(bed, np.float64).reshape(-1, 2)
    xs, ys = np.unique(bed[:, 0]), np.unique(bed[:, 1])
    pos = {tuple(p): i for i, p in enumerate(bed)}
    cells = [
        (pos[(xs[i], ys[j])], pos[(xs[i + 1], ys[j])], pos[(xs[i], ys[j + 1])], pos[(xs[i + 1], ys[j + 1])])
        for i in range(len(xs) - 1)
        for j in range(len(ys) - 1)
    ]
    best = (-1, np.inf, None)
    # ponytail: every (blob, right, lower) triple times every cell, ~1 s in Python with 40 blobs. Fine for a
    # once-per-calibration call; prune seeds by blob size or vectorise if it ever runs per frame.
    for a in range(len(und)):
        near = np.argsort(np.linalg.norm(und - und[a], axis=1))[1 : neighbours + 1]
        for b in near:
            if und[b, 0] <= und[a, 0]:
                continue
            for c in near:
                if c == b or und[c, 1] <= und[a, 1]:
                    continue
                dists = np.linalg.norm(und - (und[b] + und[c] - und[a]), axis=1)
                dists[[a, b, c]] = np.inf
                e = int(np.argmin(dists))
                # the fourth corner must sit near where the parallelogram puts it
                if dists[e] > 0.5 * min(np.linalg.norm(und[b] - und[a]), np.linalg.norm(und[c] - und[a])):
                    continue
                img = und[[a, b, c, e]].astype(np.float32)
                for cell in cells:
                    model = cv2.getPerspectiveTransform(bed[list(cell)].astype(np.float32), img)
                    if not _usable(model) or not _upright(model, bed):
                        continue
                    assign = None
                    for _ in range(iterations):
                        new = _assign(model, und, bed)
                        ok = new >= 0
                        stable = assign is not None and np.array_equal(new, assign)
                        assign = new
                        if ok.sum() < 4 or stable:
                            break
                        model, _ = cv2.findHomography(bed[ok], und[assign[ok]], 0)
                        if not _usable(model):
                            break
                    ok = assign >= 0
                    if not _usable(model) or ok.sum() < 4 or not _upright(model, bed):
                        continue
                    rms = float(np.sqrt((_residuals(model, und[assign[ok]], bed[ok]) ** 2).sum(axis=1).mean()))
                    if ok.sum() > best[0] or (ok.sum() == best[0] and rms < best[1]):
                        best = (int(ok.sum()), rms, assign.copy())
    return best[2], best[1]


def gate(matched, total, rms):
    """Decide whether a match may be used for solve-PnP.

    :param int matched: grid positions that got a blob
    :param int total: grid positions
    :param float rms: residual of the matched marks to one homography, mm (inf when nothing fitted)
    :return: None to accept, or NOT_ENOUGH_MARKS / HIGH_RESIDUAL
    """
    if matched < total:
        return NOT_ENOUGH_MARKS
    if rms > R_MAX_MM:
        return HIGH_RESIDUAL
    return None


def match_marks(blob_lists, ref_points):
    """auto_pnp_match: blobs per exposure ([x, y, size, contrast], undistorted px) -> one image point per ref point.

    :return: dict with points (per ref point, [x, y] or None), matched, rms, and reason (None when accepted)
    """
    blobs = merge_exposures(blob_lists)
    und = np.array([b[:2] for b in blobs], np.float64).reshape(-1, 2)
    assign, rms = match_grid(und, ref_points) if len(und) >= 4 else (None, np.inf)
    if assign is None:
        assign = np.full(len(ref_points), -1)
    matched = int((assign >= 0).sum())
    return {
        'points': [und[i].tolist() if i >= 0 else None for i in assign],
        'matched': matched,
        'rms': None if np.isinf(rms) else rms,
        'reason': gate(matched, len(ref_points), rms),
    }
