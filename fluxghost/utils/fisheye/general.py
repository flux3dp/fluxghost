import cv2

from .constants import T_PAD, B_PAD, L_PAD, R_PAD

def pad_image(img):
    img = cv2.copyMakeBorder(img, T_PAD, B_PAD, L_PAD, R_PAD, cv2.BORDER_CONSTANT, None, (255, 255, 255))
    return img
