import logging

from .contour_info import get_contour_info, get_rotation_kd_tree
from .find_contours import get_contour_by_canny, get_contour_by_hsv_gradient
from .group_contours import group_similar_contours


logger = logging.getLogger(__name__)


def find_similar_contours(img, is_spliced_img=False):
    canny_child_contours, canny_parent_contours = get_contour_by_canny(img, is_spliced_img=is_spliced_img)
    hsv_child_contours, hsv_parent_contours = get_contour_by_hsv_gradient(img, is_spliced_img=is_spliced_img)

    groups = []
    groups += group_similar_contours(canny_child_contours + hsv_child_contours + canny_parent_contours + hsv_parent_contours)
    groups = sorted(groups, key=lambda x: (len(x[0]), -x[2]), reverse=True)
    logger.info('Result group number: %d' % len(groups))
    if len(groups) == 0:
        return []
    group = groups[0]
    contours = group[0]
    logger.info('Most commen group contours: %d' % len(contours))
    if len(contours) <= 1:
        return []

    data = []
    base_kd_tree = get_rotation_kd_tree(contours[0])
    for i, contour in enumerate(contours):
        info = get_contour_info(contour, base_kd_tree if i > 0 else None)
        data.append(info)
    return data
