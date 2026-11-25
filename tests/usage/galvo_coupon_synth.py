"""Synthetic HEXA G galvo calibration coupon renderer (test fixture generator).

Renders the §7.2 pattern (beam-studio docs/prd/hexa-ii-galvo/
hexa-g-galvo-calibration.md) plus the 8-L nozzle frame onto a dark sheet at
a given px/mm, with a known galvo affine (scale, skew, rotation, offset) so
the solver in fluxghost/utils/camera/galvo_coupon.py can be checked against
ground truth. No hardware; numpy + OpenCV only. Also usable to produce fake
captures for the Beam Studio side, e.g. `cv2.imwrite('coupon.png', render_coupon())`.
"""

import math

import cv2
import numpy as np

PITCH = 11.0
GRID = 9
NODE_R = 1.25
ARM = (2.0, 4.5)
DISCOVERY_R = (1.5, 3.5)
IDENTITY = (-44.0, -51.0)
IDENTITY_R = 0.5
L_HALF = 70.0
L_ARM = 8.0
CIRCLE_SEGMENTS = 36


def _circle(cx, cy, r, segments=CIRCLE_SEGMENTS):
    """36-gon starting at the -Y end, first segment toward +X (closed)."""
    pts = []
    for k in range(segments + 1):
        a = -math.pi / 2 + 2 * math.pi * k / segments
        pts.append([cx + r * math.cos(a), cy + r * math.sin(a)])
    return pts


def coupon_features(pitch=PITCH, grid=GRID, identity=IDENTITY):
    """Feature centres in command mm, keyed by kind (matches §7.2).

    The defaults are the 110 lens's coupon. A smaller lens gets fewer nodes at the same
    pitch (7 x 7 on the 90 lens, 5 x 5 on the 70), the other marks keeping their place
    relative to the outer nodes, as Beam Studio's galvoCoupon.ts lays them out.
    """
    half = (grid - 1) * pitch / 2.0
    inner = pitch / 2.0
    outer = half + inner
    mid = inner + pitch * ((grid - 1) // 4)
    nodes = [[-half + i * pitch, -half + j * pitch] for j in range(grid) for i in range(grid)]
    discovery = (
        [[sx * outer, sy * outer] for sx in (1, -1) for sy in (1, -1)]
        + [[sx * inner, sy * outer] for sx in (1, -1) for sy in (1, -1)]
        + [[sx * outer, sy * inner] for sx in (1, -1) for sy in (1, -1)]
    )
    validation = [[sx * inner, sy * inner] for sx in (1, -1) for sy in (1, -1)] + [
        [sx * mid, sy * mid] for sx in (1, -1) for sy in (1, -1)
    ]
    return {'nodes': nodes, 'discovery': discovery, 'validation': validation, 'identity': [list(identity)]}


def coupon_strokes(pitch=PITCH, grid=GRID, identity=IDENTITY):
    """Polylines (command mm, no roll) of the whole galvo coupon."""
    feats = coupon_features(pitch, grid, identity)
    strokes = []
    for cx, cy in feats['nodes']:
        strokes.append(_circle(cx, cy, NODE_R))
        strokes.append([[cx - ARM[1], cy], [cx - ARM[0], cy]])
        strokes.append([[cx + ARM[0], cy], [cx + ARM[1], cy]])
        strokes.append([[cx, cy - ARM[1]], [cx, cy - ARM[0]]])
        strokes.append([[cx, cy + ARM[0]], [cx, cy + ARM[1]]])
    d = 1 / math.sqrt(2)
    for cx, cy in feats['discovery']:
        for sx, sy in ((1, 1), (-1, -1), (1, -1), (-1, 1)):
            r0, r1 = DISCOVERY_R
            strokes.append([[cx + sx * r0 * d, cy + sy * r0 * d], [cx + sx * r1 * d, cy + sy * r1 * d]])
    for cx, cy in feats['validation']:
        strokes.append(_circle(cx, cy, NODE_R))
    strokes.append(_circle(identity[0], identity[1], IDENTITY_R))
    return strokes


def l_frame_strokes(half=L_HALF, arm=L_ARM):
    """8 L polylines (bed mm relative to C): X-arm end -> vertex -> Y-arm end.

    Corner Ls point both arms toward the centre; an edge-midpoint L points the
    arm on its own axis toward + and the other arm toward the centre.
    """
    strokes = []
    for vx in (-half, 0.0, half):
        for vy in (-half, 0.0, half):
            if vx == 0.0 and vy == 0.0:
                continue
            dx = -np.sign(vx) * arm if vx != 0 else arm
            dy = -np.sign(vy) * arm if vy != 0 else arm
            strokes.append([[vx + dx, vy], [vx, vy], [vx, vy + dy]])
    return strokes


def l_frame_vertices(half=L_HALF):
    return [[vx, vy] for vx in (-half, 0.0, half) for vy in (-half, 0.0, half) if not (vx == 0.0 and vy == 0.0)]


def galvo_affine(scale_x=1.0, scale_y=1.0, skew_deg=0.0, rot_deg=0.0):
    """L = R(rot) @ U with U = [[sx, sy sin(skew)], [0, sy cos(skew)]] (the solver's QR convention)."""
    sk = math.radians(skew_deg)
    u = np.array([[scale_x, scale_y * math.sin(sk)], [0.0, scale_y * math.cos(sk)]])
    r = math.radians(rot_deg)
    rot = np.array([[math.cos(r), -math.sin(r)], [math.sin(r), math.cos(r)]])
    return rot @ u


def render_coupon(
    px_per_mm=20.0,
    size_px=(3600, 3600),
    center_px=None,
    scale_x=1.0,
    scale_y=1.0,
    skew_deg=0.0,
    rot_deg=0.0,
    offset_mm=(0.0, 0.0),
    frame_rot_deg=0.0,
    frame_px_per_mm=None,
    stroke_mm=0.4,
    bg=30,
    fg=230,
    color=False,
    drop_l=(),
    noise=0.0,
    seed=0,
    grid=GRID,
    identity=IDENTITY,
    square_mm=None,
):
    """Render a coupon + L frame image (BGR uint8).

    Galvo marks: px = C + F @ (L @ c + offset), with L from `galvo_affine` and
    F the frame (ruler) transform: `frame_px_per_mm` (x, y) rotated by
    `frame_rot_deg`. L frame: px = C + F @ v. `drop_l` lists vertex indices
    (order of `l_frame_vertices`) to leave out. `color=True` draws galvo marks
    greenish-white and the L frame reddish (green channel below 150) so the
    threshold sequence is exercised. `grid` and `identity` draw a smaller lens's coupon;
    `square_mm` adds the square the calibration marks on the same sheet.
    """
    w, h = size_px
    if center_px is None:
        center_px = (w / 2.0, h / 2.0)
    if frame_px_per_mm is None:
        frame_px_per_mm = (px_per_mm, px_per_mm)
    fr = math.radians(frame_rot_deg)
    frame = np.array([[math.cos(fr), -math.sin(fr)], [math.sin(fr), math.cos(fr)]]) @ np.diag(frame_px_per_mm)
    l_mat = galvo_affine(scale_x, scale_y, skew_deg, rot_deg)
    offset = np.asarray(offset_mm, dtype=np.float64)
    centre = np.asarray(center_px, dtype=np.float64)

    img = np.full((h, w, 3), bg, np.uint8)
    thickness = max(1, round(stroke_mm * px_per_mm))
    shift = 4
    scale = 1 << shift

    def draw(strokes, transform, colour):
        for stroke in strokes:
            pts = np.array([transform(np.asarray(pt, dtype=np.float64)) for pt in stroke])
            pts = np.round(pts * scale).astype(np.int32).reshape(-1, 1, 2)
            cv2.polylines(img, [pts], False, colour, thickness, cv2.LINE_AA, shift)

    galvo_colour = (210, 240, 210) if color else (fg, fg, fg)
    l_colour = (140, 140, 220) if color else (fg, fg, fg)
    galvo_strokes = coupon_strokes(grid=grid, identity=identity)
    if square_mm:
        e = square_mm / 2.0
        galvo_strokes.append([[-e, -e], [e, -e], [e, e], [-e, e], [-e, -e]])
    draw(galvo_strokes, lambda c: centre + frame @ (l_mat @ c + offset), galvo_colour)
    l_strokes = [s for k, s in enumerate(l_frame_strokes()) if k not in set(drop_l)]
    draw(l_strokes, lambda v: centre + frame @ v, l_colour)
    if noise > 0:
        rng = np.random.default_rng(seed)
        img = np.clip(img.astype(np.float64) + rng.normal(0, noise, img.shape), 0, 255).astype(np.uint8)
    return img
