import cv2
import numpy as np


def calculate_hu_moments(contours):
    hu_moments = []
    for contour in contours:
        moments = cv2.moments(contour)
        hu_moments.append(cv2.HuMoments(moments).flatten())
    return hu_moments


# https://docs.opencv.org/4.x/d3/dc0/group__imgproc__shape.html#gaf2b97a230b51856d09a2d934b78c015f
def normalize_hu_moments(hu_moments):
    """
    basically like openCV log transform
    but hu[4], hu[5] may be very small with different sign,
    so we use the absolute value to normalize
    hu[6] is ignored cause it's so different for the same shapes
    """
    return np.array(
        [
            -np.sign(hu_moments[0]) / np.log10(np.abs(hu_moments[0])),
            -np.sign(hu_moments[1]) / np.log10(np.abs(hu_moments[1])),
            -np.sign(hu_moments[2]) / np.log10(np.abs(hu_moments[2])),
            -np.sign(hu_moments[3]) / np.log10(np.abs(hu_moments[3])),
            -1 / np.log10(np.abs(hu_moments[4])),
            -1 / np.log10(np.abs(hu_moments[5])),
        ]
    )


def calculate_hu_moments_dist(hu_moments1, hu_moments2):
    normalized1 = normalize_hu_moments(hu_moments1)
    normalized2 = normalize_hu_moments(hu_moments2)
    dist = np.linalg.norm(normalized1 - normalized2, ord=1)
    return dist


def calculate_area_difference(area1, area2):
    return abs(area1 - area2) / max(area1, area2)


def check_area_difference(area1, area2, threshold=0.2):
    return calculate_area_difference(area1, area2) < threshold


def check_bbox_intersect(bbox1, bbox2):
    x1, y1, w1, h1 = bbox1
    x2, y2, w2, h2 = bbox2

    overlap_x = max(x1, x2) < min(x1 + w1, x2 + w2)
    overlap_y = max(y1, y2) < min(y1 + h1, y2 + h2)
    return overlap_x and overlap_y


def check_area_intersect(contour1, contour2, w, h):
    mask1 = np.zeros((h, w), np.uint8)
    mask2 = np.zeros((h, w), np.uint8)
    cv2.drawContours(mask1, [contour1], -1, 255, thickness=cv2.FILLED)
    cv2.drawContours(mask2, [contour2], -1, 255, thickness=cv2.FILLED)
    # or less than certain threshold
    return cv2.countNonZero(cv2.bitwise_and(mask1, mask2)) > 0


def calculate_smoothness(contour):
    perimeter = cv2.arcLength(contour, True)
    area = cv2.contourArea(contour)
    # the higher the smoother
    return np.sqrt(area) / perimeter


def check_contour_intersection(contour1, contour2):
    bbox1 = cv2.boundingRect(contour1)
    bbox2 = cv2.boundingRect(contour2)
    if not check_bbox_intersect(bbox1, bbox2):
        return False
    min_x = min(bbox1[0], bbox2[0])
    min_y = min(bbox1[1], bbox2[1])
    max_x = max(bbox1[0] + bbox1[2], bbox2[0] + bbox2[2])
    max_y = max(bbox1[1] + bbox1[3], bbox2[1] + bbox2[3])
    contour1 = contour1.copy() - (min_x, min_y)
    contour2 = contour2.copy() - (min_x, min_y)
    w = max_x - min_x
    h = max_y - min_y
    return check_area_intersect(contour1, contour2, w, h)


def group_similar_contours(contours, hu_threshold=0.15, area_threshold=0.25):
    groups = []
    hu_moments = calculate_hu_moments(contours)
    areas = [abs(cv2.contourArea(contour)) for contour in contours]
    pairs = []

    for i in range(len(contours)):
        hu_moment = hu_moments[i]
        area = areas[i]
        for j in range(i + 1, len(contours)):
            hu_dist = calculate_hu_moments_dist(hu_moment, hu_moments[j])
            if hu_dist >= hu_threshold:
                continue
            if not check_area_difference(area, areas[j], area_threshold):
                continue
            pairs.append((i, j))
    group_id_map = {}
    group_count = 0
    for i, j in pairs:
        if i in group_id_map and j in group_id_map:
            group_id_map[i] = min(group_id_map[i], group_id_map[j])
            group_id_map[j] = min(group_id_map[i], group_id_map[j])
        elif i in group_id_map:
            group_id_map[j] = group_id_map[i]
        elif j in group_id_map:
            group_id_map[i] = group_id_map[j]
        else:
            group_id_map[i] = group_count
            group_id_map[j] = group_count
            group_count += 1
    groups_map = {}
    for i in group_id_map:
        group_idx = group_id_map[i]
        if group_idx not in groups_map:
            groups_map[group_idx] = ([], [], 0)
        groups_map[group_idx][0].append(contours[i])
        groups_map[group_idx][1].append(hu_moments[i])
    groups = list(groups_map.values())

    for group_idx, group in enumerate(groups):
        group_contours, group_hu_moments, _ = group
        idx_to_remove = []
        remaining = len(group_contours)
        if remaining <= 1:
            continue
        smoothness_list = [calculate_smoothness(c) for c in group_contours]

        for i in range(len(group_contours)):
            if i in idx_to_remove:
                continue
            for j in range(i + 1, len(group_contours)):
                if j in idx_to_remove:
                    continue
                if check_contour_intersection(group_contours[i], group_contours[j]):
                    smoothness_i = smoothness_list[i]
                    smoothness_j = smoothness_list[j]
                    if smoothness_i > smoothness_j:
                        idx_to_remove.append(j)
                        remaining -= 1
                    else:
                        idx_to_remove.append(i)
                        remaining -= 1
                        break
        group_contours = [contour for idx, contour in enumerate(group_contours) if idx not in idx_to_remove]
        group_hu_moments = np.array(
            [hu_moment for idx, hu_moment in enumerate(group_hu_moments) if idx not in idx_to_remove]
        )
        smoothness_list = [smoothness for idx, smoothness in enumerate(smoothness_list) if idx not in idx_to_remove]
        group_similarity = np.std(smoothness_list) / np.mean(smoothness_list)
        groups[group_idx] = (group_contours, group_hu_moments, group_similarity)

    return groups
