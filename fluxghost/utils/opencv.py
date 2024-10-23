import cv2


def findContours(*args, **kwargs):
    res = cv2.findContours(*args, **kwargs)
    if len(res) == 2:
        return res
    return res[1:]
