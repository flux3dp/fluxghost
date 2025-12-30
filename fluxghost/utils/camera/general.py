import cv2

from .constants import B_PAD, IMAGE_H, IMAGE_W, L_PAD, R_PAD, T_PAD


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
