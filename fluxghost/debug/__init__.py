import os

import cv2

WRITE_DEBUG_IMG = os.environ.get('GHOST_DEBUG_IMG', '').lower() in ('1', 'true', 'yes')
DEBUG_IMG_DIR = os.environ.get('GHOST_DEBUG_IMG_DIR', 'debug-imgs')


def debug_imwrite(path, img):
    if not WRITE_DEBUG_IMG:
        return
    full_path = os.path.join(DEBUG_IMG_DIR, path)
    os.makedirs(os.path.dirname(full_path) or '.', exist_ok=True)
    cv2.imwrite(full_path, img)
