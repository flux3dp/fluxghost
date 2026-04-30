import logging
import math
import random

import cv2
import numpy as np

from fluxghost.debug import WRITE_DEBUG_IMG, debug_imwrite

from .contour_data import ContourData
from .contour_info import get_contour_info, get_rotation_kd_tree
from .find_contours import get_contour_by_canny, get_contour_by_hsv_gradient
from .group_contours import group_similar_contours

logger = logging.getLogger(__name__)


def write_all_contours_debug_image(img, contour_data_list, suffix=''):
    if not WRITE_DEBUG_IMG:
        return
    img_copy = img.copy()
    for cd in contour_data_list:
        bbox = cv2.boundingRect(cd.contour)
        center = (bbox[0] + bbox[2] // 2, bbox[1] + bbox[3] // 2)
        color = (int(256 * random.random()), int(256 * random.random()), int(256 * random.random()), 255)
        cv2.drawContours(img_copy, [cd.contour], -1, color, thickness=5)
        cv2.putText(img_copy, str(cd.index), center, cv2.FONT_HERSHEY_SIMPLEX, 2, color, 5)
    debug_imwrite(f'similar-contours-all{suffix}.png', img_copy)


def write_group_contours_debug_image(img, data, suffix=''):
    if not WRITE_DEBUG_IMG:
        return
    img_copy = img.copy()
    for group_data in data:
        color = (int(256 * random.random()), int(256 * random.random()), int(256 * random.random()), 255)
        for info in group_data:
            contour = np.array(info['contour'], dtype=np.int32).reshape(-1, 1, 2)
            cv2.drawContours(img_copy, [contour], -1, color, thickness=3)
            cv2.circle(img_copy, info['center'], 3, color, -1)
            cv2.line(
                img_copy,
                info['center'],
                (
                    info['center'][0] + int(100 * math.cos(info['angle'])),
                    info['center'][1] + int(100 * math.sin(info['angle'])),
                ),
                color,
                3,
            )
    debug_imwrite(f'similar-contours-groups{suffix}.png', img_copy)


def handle_transparent_image(img):
    """
    Handle transparent image, currently Canny ignore alpha channel and treat it as original color, which may cause
    contours not detected.
    So we fill transparent area with inverse of average color to make it more likely to be detected.
    May change to average color of nearby non-transparent pixels in the future.
    """
    if img.shape[2] > 3:
        transparent_mask = img[:, :, 3] == 0
        non_transparent_mask = ~transparent_mask
        avg_color = cv2.mean(img, mask=non_transparent_mask.astype('uint8'))[:3]
        img[transparent_mask] = [255 - avg_color[0], 255 - avg_color[1], 255 - avg_color[2], 255]


def find_similar_contours(img, is_spliced_img=False, all_groups=False, suffix=''):
    handle_transparent_image(img)

    canny_child_contours, canny_parent_contours = get_contour_by_canny(img, is_spliced_img=is_spliced_img)
    hsv_child_contours, hsv_parent_contours = get_contour_by_hsv_gradient(img, is_spliced_img=is_spliced_img)

    contour_data_list = []
    i = 0
    for label, priority, contours in [
        ('canny child', 2, canny_child_contours),
        ('canny parent', 2, canny_parent_contours),
        ('hsv child', 1, hsv_child_contours),
        ('hsv parent', 1, hsv_parent_contours),
    ]:
        for contour in contours:
            contour_data_list.append(ContourData(contour, i, source=label, priority=priority))
            i += 1

    write_all_contours_debug_image(img, contour_data_list, suffix=suffix)

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
        write_group_contours_debug_image(img, data, suffix=suffix)
        return data
