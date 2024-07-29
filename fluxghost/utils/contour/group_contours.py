import cv2
import numpy as np


def calculate_hu_moments(contours):
    hu_moments = []
    for contour in contours:
        moments = cv2.moments(contour)
        hu_moments.append(cv2.HuMoments(moments).flatten())
    return hu_moments


# https://docs.opencv.org/4.x/d3/dc0/group__imgproc__shape.html#gaf2b97a230b51856d09a2d934b78c015f
def calculate_hu_moments_dist(hu_moments1, hu_moments2):
    # tried log transformation, but not performing well
    dist = np.linalg.norm(hu_moments1 - hu_moments2, ord=1)
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


def group_similar_contours(contours, hu_threshold=0.015, area_threshold=0.25):
    groups = []
    hu_moments = calculate_hu_moments(contours)

    for i, (hu_moment, contour) in enumerate(zip(hu_moments, contours)):
        group_idx = -1
        area = abs(cv2.contourArea(contour))
        for j in range(len(groups)):
            group_contours, group_hu_moments, avg_hu_moment, avg_area = groups[j]
            if calculate_hu_moments_dist(hu_moment, avg_hu_moment) < hu_threshold and check_area_difference(
                area, avg_area, area_threshold
            ):
                avg_hu_moment = (avg_hu_moment * len(group_contours) + hu_moment) / (len(group_contours) + 1)
                avg_area = (avg_area * len(group_contours) + area) / (len(group_contours) + 1)
                group_contours.append(contour)
                group_hu_moments.append(hu_moment)
                groups[j] = (group_contours, group_hu_moments, avg_hu_moment, avg_area)
                group_idx = j
                break
        if group_idx == -1:
            groups.append(([contour], [hu_moment], hu_moment, area))

    for i in range(len(groups)):
        if len(groups[i][0]) == 0:
            continue
        for j in range(i + 1, len(groups)):
            group1 = groups[i]
            group2 = groups[j]
            if calculate_hu_moments_dist(group1[2], group2[2]) < hu_threshold and check_area_difference(
                group1[3], group2[3], area_threshold
            ):
                print(f"Group {i} and {j} are similar")
                group1_contours, group1_hu_moments, _, _ = group1
                group2_contours, group2_hu_moments, _, _ = group2
                groups[i] = (
                    group1_contours + group2_contours,
                    group1_hu_moments + group2_hu_moments,
                    (group1[2] * len(group1_contours) + group2[2] * len(group2_contours))
                    / (len(group1_contours) + len(group2_contours)),
                    (group1[3] * len(group1_contours) + group2[3] * len(group2_contours))
                    / (len(group1_contours) + len(group2_contours)),
                )
                groups[j] = ([], [], 0, 0)

    for group_idx, group in enumerate(groups):
        group_contours, group_hu_moments, avg_hu_moment, avg_area = group
        idx_to_remove = []
        for i in range(len(group_contours)):
            for j in range(i + 1, len(group_contours)):
                if check_contour_intersection(group_contours[i], group_contours[j]):
                    hu_score_i = -calculate_hu_moments_dist(group_hu_moments[i], avg_hu_moment)
                    hu_score_j = -calculate_hu_moments_dist(group_hu_moments[j], avg_hu_moment)
                    if hu_score_i > hu_score_j:
                        idx_to_remove.append(j)
                    else:
                        idx_to_remove.append(i)
                        break
        group_contours = [contour for idx, contour in enumerate(group_contours) if idx not in idx_to_remove]
        group_hu_moments = [hu_moment for idx, hu_moment in enumerate(group_hu_moments) if idx not in idx_to_remove]
        groups[group_idx] = (group_contours, group_hu_moments, avg_hu_moment, avg_area)
    return groups
