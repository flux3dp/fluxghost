import io

import cv2
from PIL import Image, ImageOps

from .constants import B_PAD, IMAGE_H, IMAGE_W, L_PAD, R_PAD, T_PAD


def open_frame(buf):
    """Decode an uploaded image with its EXIF orientation applied.

    The HEXA II galvo head mounts its camera upside down, and the device tags
    every frame with EXIF Orientation=3 instead of rotating the pixels (that
    would cost it ~2 s per 8M frame). Browsers apply the tag on their own, so
    Beam Studio shows the frame upright; np.array / cv2 drop it. Every consumer
    of camera pixels here (preview, calibration, detection) goes through this
    so they all agree with what the user sees, and a k/d/rvec/tvec set stays
    valid across all of them. A no-op for images without an orientation --
    every other model, and the PNGs Beam Studio renders from a canvas.
    """
    return ImageOps.exif_transpose(Image.open(io.BytesIO(buf)))


def pad_image(img, color=(255, 255, 255)):
    img = cv2.copyMakeBorder(img, T_PAD, B_PAD, L_PAD, R_PAD, cv2.BORDER_CONSTANT, None, color)
    return img


def pad_low_resolution_image(img, color=(255, 255, 255)):
    h, w = img.shape[:2]
    if h == IMAGE_H and w == IMAGE_W:
        return pad_image(img, color)
    horizontal_ratio = w / IMAGE_W
    vertical_ratio = h / IMAGE_H
    l_pad, r_pad = round(L_PAD * horizontal_ratio), round(R_PAD * horizontal_ratio)
    t_pad, b_pad = round(T_PAD * vertical_ratio), round(B_PAD * vertical_ratio)
    img = cv2.copyMakeBorder(img, t_pad, b_pad, l_pad, r_pad, cv2.BORDER_CONSTANT, None, color)
    return img
