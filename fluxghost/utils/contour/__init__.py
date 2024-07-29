import logging

from .find_contours import get_contour_by_canny, get_contour_by_hsv_gradient
from .group_contours import group_similar_contours
from .contour_info import get_contour_info


logger = logging.getLogger(__name__)


def find_similar_contours(img, splicing_img=False):
    contours = []
    contours += get_contour_by_hsv_gradient(img, splicing_img=splicing_img)
    if splicing_img:
        contours += get_contour_by_canny(img)

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

    data = []
    for contour in contours:
        data.append(get_contour_info(contour))
    return data
