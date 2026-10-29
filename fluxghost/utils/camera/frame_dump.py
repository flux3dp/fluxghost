"""Keep a copy of the frames a measurement asked for, on the computer running fluxghost.

The galvo calibration capture (Beam Studio, `require_frame d<dpmm>`) stitches
25 patches into one image and the solver reports on that; when it fails there
is no way back to the photographs the patches were cut from. So each frame
asked for at an explicit px/mm is written out as it came from the device and
as it was sent back, numbered in the order they arrived:

    ~/Downloads/fluxghost-frames/20261029-143012/01-raw.jpg
    ~/Downloads/fluxghost-frames/20261029-143012/01-remap.jpg

One folder per camera connection, named for its first frame. Plain previews
(`require_frame`, `require_frame l`) are never written.

The client then adds what it made of them with `save_galvo_capture` on the
opencv endpoint: the stitched image, a capture.json saying where each frame
was taken and which rectangle of it was kept, and -- cut here from the saved
remaps, so they are exactly what the client stitched -- one NN-patch.png per
frame. The three stages are then side by side for a look at whether the L
marks and the nodes survive each one.

FLUXGHOST_FRAME_DUMP=0 turns it off; FLUXGHOST_FRAME_DUMP_DIR moves it. A
failure to write is logged and the frame is still sent: a missing copy must
never cost a capture.
"""

import glob
import io
import json
import logging
import os
import time

from PIL import Image

logger = logging.getLogger('API.CAMERA.DUMP')

DEFAULT_DIR = os.path.join('~', 'Downloads', 'fluxghost-frames')

# The folder the last frame went to, whichever connection wrote it: the
# stitched capture arrives on another websocket and belongs with its frames.
_latest_folder = None


def latest_folder():
    return _latest_folder


def is_enabled():
    return os.environ.get('FLUXGHOST_FRAME_DUMP', '1').strip().lower() not in ('0', 'false', 'no', 'off')


def base_dir():
    return os.path.expanduser(os.environ.get('FLUXGHOST_FRAME_DUMP_DIR') or DEFAULT_DIR)


class FrameDump:
    """Writes the frames of one camera connection; makes its folder on the first one."""

    def __init__(self, enabled=None, root=None):
        self.enabled = is_enabled() if enabled is None else enabled
        self.root = root
        self.folder = None
        self.count = 0

    def save(self, raw, remap=None, dpmm=None):
        """Write `raw` (the device's JPEG) and `remap` (what the client gets), if any.

        Returns the folder written to, or None when nothing was written.
        """
        if not self.enabled:
            return None
        try:
            if self.folder is None:
                root = self.root or base_dir()
                self.folder = os.path.join(root, time.strftime('%Y%m%d-%H%M%S'))
                os.makedirs(self.folder, exist_ok=True)
            self.count += 1
            suffix = '' if dpmm is None else '-%dppm' % dpmm
            with open(os.path.join(self.folder, '%02d-raw.jpg' % self.count), 'wb') as f:
                f.write(raw)
            if remap is not None:
                with open(os.path.join(self.folder, '%02d-remap%s.jpg' % (self.count, suffix)), 'wb') as f:
                    f.write(remap)
            logger.info('frame %d written to %s', self.count, self.folder)
            global _latest_folder
            _latest_folder = self.folder
            return self.folder
        except Exception:
            logger.exception('could not write frame %d', self.count)
            return None


def save_capture(folder, stitched, meta):
    """Put the client's side of a capture next to its frames.

    `stitched` is the stitched image's bytes (PNG), written as stitched.png;
    `meta` is written as capture.json. For each entry of meta['tiles'] that
    names a `frame` (1-based, the frame's number in this folder) and a `rect`
    {sx, sy, sw, sh} in that frame's remap pixels, the rectangle is cut from
    NN-remap-*.jpg and written as NN-patch.png -- the pixels the client
    stitched, as it stitched them. Returns the names written.
    """
    written = []
    with open(os.path.join(folder, 'stitched.png'), 'wb') as f:
        f.write(stitched)
    written.append('stitched.png')
    with open(os.path.join(folder, 'capture.json'), 'w') as f:
        json.dump(meta, f, indent=2, sort_keys=True)
    written.append('capture.json')
    for tile in meta.get('tiles') or []:
        frame, rect = tile.get('frame'), tile.get('rect')
        if not frame or not rect:
            continue
        remaps = sorted(glob.glob(os.path.join(folder, '%02d-remap*.jpg' % int(frame))))
        if not remaps:
            logger.warning('no remap for frame %s to cut the patch from', frame)
            continue
        sx, sy = round(rect['sx']), round(rect['sy'])
        sw, sh = round(rect['sw']), round(rect['sh'])
        name = '%02d-patch.png' % int(frame)
        with Image.open(remaps[0]) as img:
            img.crop((sx, sy, sx + sw, sy + sh)).save(os.path.join(folder, name))
        written.append(name)
    logger.info('capture written to %s: %s', folder, ', '.join(written))
    return written
