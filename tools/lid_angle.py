"""Lid-angle study behind the camera pose check (beam-studio docs/prd/auto-full-area-preview-pose-check.md §2.3).

Reads one or more folders of raw camera frames named <epoch_ms>.jpg (written by the local frame-dump
patch in fluxghost/api/camera.py) and writes, per folder, a CSV with one row per frame:

  t_ms        time since the first frame of the folder
  left_deg    angle from vertical of the longest near-vertical edge segment in the left outer band
  right_deg   same for the right outer band (positive = lower end to the right of the upper end, as in
              fluxghost/utils/camera/pose_check.py)
  conv_deg    right_deg - left_deg: side-rim convergence, the pose signal
  left_len    height of the chosen left rim segment as a fraction of the frame height (right_len likewise)
  front_y     y (fraction of height) of the longest near-horizontal segment in the front band (0.6-0.9), >= 40% wide
  motion      mean abs gray difference to the previous frame, 0-255 (the stillness baseline)
  sharp       variance of the Laplacian (blur gate: a lid moving during the exposure flattens it)
  n_lines     Hough segments kept, as a sanity check on the overlays

With --overlay, also writes <folder>/overlay/<frame>.png with the chosen segments drawn, which is how
to confirm the segments are the chassis rim and not the honeycomb or a hand. With --plot (needs
matplotlib: `uv run --with matplotlib python tools/lid_angle.py --plot ...`) writes <folder>/lid_angle.png.

Usage: uv run python tools/lid_angle.py frame-dump/20261106-101500 [more folders] [--overlay] [--plot]
"""

import argparse
import csv
import math
import os
import sys

import cv2
import numpy as np

MAX_WIDTH = 1280
CANNY = (50, 150)
MIN_LINE_FRAC = 0.08  # ponytail: a segment counts if longer than 8% of the width; tune on real frames
SIDE_MAX_DEG = 35  # near-vertical: within 35 degrees of vertical
FRONT_MAX_DEG = 20  # near-horizontal: within 20 degrees of horizontal
SIDE_BAND = 0.12  # side rim lives in the outer 12% of the width; the honeycomb ruler sticker sits at ~82%
FRONT_BAND = (
    0.6,
    0.9,
)  # bed front edge sits at ~0.75 of the height when open; paper edges and the lower rail are outside
FRONT_MIN_FRAC = 0.4  # the front edge spans most of the width even with a hand over it


def load_gray(path):
    img = cv2.imread(path)
    if img is None:
        return None, None
    h, w = img.shape[:2]
    if w > MAX_WIDTH:
        scale = MAX_WIDTH / w
        img = cv2.resize(img, (MAX_WIDTH, int(h * scale)), interpolation=cv2.INTER_AREA)
    return img, cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def segments(gray):
    edges = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), *CANNY)
    min_len = int(gray.shape[1] * MIN_LINE_FRAC)
    lines = cv2.HoughLinesP(edges, 1, math.radians(1), 80, minLineLength=min_len, maxLineGap=10)
    out = []
    for x1, y1, x2, y2 in lines[:, 0] if lines is not None else []:
        length = math.hypot(x2 - x1, y2 - y1)
        angle = math.degrees(math.atan2(y2 - y1, x2 - x1))  # -180..180, 0 = horizontal
        out.append(((x1, y1, x2, y2), length, angle))
    return out


def from_vertical(angle):
    """Signed degrees from vertical: 0 = vertical, positive = lower end to the right of the upper end."""
    a = angle % 180  # 0..180
    return 90 - a  # a=90 is vertical


def pick(segs, keep, key):
    cands = [s for s in segs if keep(s)]
    return max(cands, key=key) if cands else None


def measure(gray, segs):
    h, w = gray.shape

    def is_side(s):
        (x1, y1, x2, y2), _, angle = s
        return abs(from_vertical(angle)) <= SIDE_MAX_DEG

    def is_front(s):
        (x1, y1, x2, y2), _, angle = s
        a = abs(angle % 180)
        y = (y1 + y2) / 2 / h
        return min(a, 180 - a) <= FRONT_MAX_DEG and FRONT_BAND[0] <= y <= FRONT_BAND[1] and s[1] >= w * FRONT_MIN_FRAC

    left = pick(segs, lambda s: is_side(s) and (s[0][0] + s[0][2]) / 2 < w * SIDE_BAND, lambda s: s[1])
    right = pick(segs, lambda s: is_side(s) and (s[0][0] + s[0][2]) / 2 > w * (1 - SIDE_BAND), lambda s: s[1])
    front = pick(segs, is_front, lambda s: s[1])
    left_deg = from_vertical(left[2]) if left else None
    right_deg = from_vertical(right[2]) if right else None
    conv = right_deg - left_deg if left and right else None
    front_y = (front[0][1] + front[0][3]) / 2 / h if front else None
    lens = tuple(abs(s[0][3] - s[0][1]) / h if s else None for s in (left, right))  # rim segment height, fraction of h
    return {'left': left, 'right': right, 'front': front}, left_deg, right_deg, conv, front_y, lens


def draw_overlay(img, chosen, path):
    out = img.copy()
    for name, color in (('left', (0, 255, 0)), ('right', (0, 200, 255)), ('front', (255, 0, 255))):
        s = chosen[name]
        if s:
            (x1, y1, x2, y2), _, _ = s
            cv2.line(out, (x1, y1), (x2, y2), color, 3)
            cv2.putText(out, name, (x1, y1), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
    cv2.imwrite(path, out)


def frame_time(path):
    stem = os.path.splitext(os.path.basename(path))[0]
    try:
        return int(stem)
    except ValueError:
        return None


def process(folder, overlay, plot):
    files = sorted(f for f in os.listdir(folder) if f.lower().endswith('.jpg'))
    paths = [os.path.join(folder, f) for f in files]
    if not paths:
        print(f'{folder}: no .jpg frames', file=sys.stderr)
        return
    t0 = frame_time(paths[0])
    rows = []
    prev_gray = None
    overlay_dir = os.path.join(folder, 'overlay')
    if overlay:
        os.makedirs(overlay_dir, exist_ok=True)
    for i, path in enumerate(paths):
        img, gray = load_gray(path)
        if gray is None:
            continue
        segs = segments(gray)
        chosen, left_deg, right_deg, conv, front_y, (left_len, right_len) = measure(gray, segs)
        motion = float(np.mean(cv2.absdiff(gray, prev_gray))) if prev_gray is not None else None
        sharp = float(cv2.Laplacian(gray, cv2.CV_64F).var())  # motion blur during a lid move flattens this
        prev_gray = gray
        t = frame_time(path)
        rows.append(
            {
                'frame': os.path.basename(path),
                't_ms': (t - t0) if t is not None and t0 is not None else i,
                'left_deg': left_deg,
                'right_deg': right_deg,
                'conv_deg': conv,
                'left_len': left_len,
                'right_len': right_len,
                'front_y': front_y,
                'motion': motion,
                'sharp': sharp,
                'n_lines': len(segs),
            }
        )
        if overlay:
            draw_overlay(img, chosen, os.path.join(overlay_dir, os.path.splitext(os.path.basename(path))[0] + '.png'))

    csv_path = os.path.join(folder, 'lid_angle.csv')
    with open(csv_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    def fmt(v, p=1):
        return '-' if v is None else f'{v:.{p}f}'

    print(f'\n{folder} ({len(rows)} frames) -> {csv_path}')
    print(
        f'{"t_ms":>7} {"left":>6} {"right":>6} {"conv":>6} {"l_len":>5} {"r_len":>5} '
        f'{"front_y":>7} {"motion":>6} {"sharp":>6} {"lines":>5}'
    )
    for r in rows:
        print(
            f'{r["t_ms"]:>7} {fmt(r["left_deg"]):>6} {fmt(r["right_deg"]):>6} {fmt(r["conv_deg"]):>6} '
            f'{fmt(r["left_len"], 2):>5} {fmt(r["right_len"], 2):>5} '
            f'{fmt(r["front_y"], 3):>7} {fmt(r["motion"]):>6} {fmt(r["sharp"], 0):>6} {r["n_lines"]:>5}'
        )

    if plot:
        try:
            import matplotlib as mpl

            mpl.use('Agg')
            import matplotlib.pyplot as plt
        except ImportError:
            print('matplotlib missing: run with `uv run --with matplotlib python tools/lid_angle.py`', file=sys.stderr)
            return
        t = [r['t_ms'] / 1000 for r in rows]
        fig, (ax1, ax2) = plt.subplots(2, 1, sharex=True, figsize=(10, 6))
        ax1.plot(t, [r['conv_deg'] if r['conv_deg'] is not None else np.nan for r in rows], 'o-', label='conv_deg')
        ax1.plot(t, [r['front_y'] * 100 if r['front_y'] is not None else np.nan for r in rows], 's-', label='front_y')
        ax1.legend()
        ax1.set_ylabel('pose signals')
        ax2.plot(t, [r['motion'] if r['motion'] is not None else np.nan for r in rows], 'o-', color='gray')
        ax2.set_ylabel('motion')
        ax2.set_xlabel('s since first frame')
        fig.suptitle(os.path.basename(folder.rstrip('/')))
        fig.savefig(os.path.join(folder, 'lid_angle.png'), dpi=120)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('folders', nargs='+')
    ap.add_argument('--overlay', action='store_true', help='write overlay/<frame>.png with the chosen segments')
    ap.add_argument('--plot', action='store_true', help='write lid_angle.png (needs matplotlib)')
    args = ap.parse_args()
    for folder in args.folders:
        process(folder, args.overlay, args.plot)


if __name__ == '__main__':
    main()
