import logging

from .find_contours import get_contour_by_canny, get_contour_by_hsv_gradient
from .group_contours import group_similar_contours
from .contour_info import get_contour_info


logger = logging.getLogger(__name__)


def find_similar_contours(img):
    contours = []
    # contours += get_contour_by_canny(img.copy())
    contours += get_contour_by_hsv_gradient(img.copy())

    if len(contours) == 0:
        return []

    groups = group_similar_contours(contours)
    groups = sorted(groups, key=lambda x: len(x[0]), reverse=True)
    logger.info('Result group number: %d' % len(groups))
    if len(groups) == 0:
        return []
    group = groups[0]
    contours = group[0]
    logger.info('Most commen group contours: %d' % len(contours))

    group_img = img.copy()
    data = []
    for contour in contours:
        import cv2
        cv2.drawContours(group_img, [contour], -1, (0, 255, 0), thickness=2)
        data.append(get_contour_info(contour))
    return data
