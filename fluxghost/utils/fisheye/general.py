import cv2

from .constants import B_PAD, L_PAD, R_PAD, T_PAD


def pad_image(img, color=(255, 255, 255)):
    img = cv2.copyMakeBorder(img, T_PAD, B_PAD, L_PAD, R_PAD, cv2.BORDER_CONSTANT, None, color)
    return img
