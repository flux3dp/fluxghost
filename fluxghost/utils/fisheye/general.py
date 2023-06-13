import cv2

DPMM = 5
T_PAD = 1000
B_PAD = 1000
L_PAD = 1300
R_PAD = 1580
CHESSBORAD = (48, 36)
PERSPECTIVE_SPLIT = (15, 15)

def pad_image(img):
    img = cv2.copyMakeBorder(img, T_PAD, B_PAD, L_PAD, R_PAD, cv2.BORDER_CONSTANT, None, (255, 255, 255))
    return img
