import logging

from .contour_data import ContourData
from .contour_info import get_contour_info, get_rotation_kd_tree
from .find_contours import get_contour_by_canny, get_contour_by_hsv_gradient
from .group_contours import group_similar_contours

logger = logging.getLogger(__name__)


def find_similar_contours(img, is_spliced_img=False, all_groups=False):
    canny_child_contours, canny_parent_contours = get_contour_by_canny(img, is_spliced_img=is_spliced_img)
    hsv_child_contours, hsv_parent_contours = get_contour_by_hsv_gradient(img, is_spliced_img=is_spliced_img)

    contour_data_list = []
    i = 0
    for label, priority, list in [
        ('canny child', 2, canny_child_contours),
        ('canny parent', 2, canny_parent_contours),
        ('hsv child', 1, hsv_child_contours),
        ('hsv parent', 1, hsv_parent_contours),
    ]:
        logger.info(f'{label} contour number: {len(list)}')
        for contour in list:
            contour_data_list.append(ContourData(contour, i, source=label, priority=priority))
            i += 1

    groups = group_similar_contours(contour_data_list)
    groups = [group for group in groups if len(group[0]) > 1]
    groups = sorted(groups, key=lambda x: (len(x[0]), -x[1]), reverse=True)
    logger.info('Result group number: %d' % len(groups))
    if len(groups) == 0:
        return []
    if not all_groups:
        group = groups[0]
        contour_data_list = group[0]
        logger.info('Most common group contours: %d' % len(contour_data_list))
        data = []
        base_kd_tree = get_rotation_kd_tree(contour_data_list[0].contour)
        for i, cd in enumerate(contour_data_list):
            info = get_contour_info(cd, base_kd_tree if i > 0 else None)
            data.append(info)
        return data
    else:
        data = []
        for i, group in enumerate(groups):
            contour_data_list = group[0]
            logger.info('Group #%d contours: %d' % (i, len(contour_data_list)))
            group_data = []
            base_kd_tree = get_rotation_kd_tree(contour_data_list[0].contour)
            for j, cd in enumerate(contour_data_list):
                info = get_contour_info(cd, base_kd_tree if j > 0 else None, include_contour=True)
                group_data.append(info)
            data.append(group_data)
        return data
