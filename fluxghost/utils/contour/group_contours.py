import logging

import cv2
import numpy as np

from .contour_data import ContourData

logger = logging.getLogger(__name__)


def calculate_hu_moments_dist(cd1: ContourData, cd2: ContourData):
    return np.linalg.norm(cd1.normalized_hu_moments - cd2.normalized_hu_moments, ord=1)


def calculate_area_ratio(area1, area2):
    return min(area1, area2) / max(area1, area2)


def check_area_difference(area1, area2, threshold):
    return calculate_area_ratio(area1, area2) >= threshold


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


def group_similar_contours(contour_data_list, hu_threshold=0.15, min_area_ratio=0.5):
    pairs = []

    for i in range(len(contour_data_list)):
        cd_i = contour_data_list[i]
        for j in range(i + 1, len(contour_data_list)):
            cd_j = contour_data_list[j]
            hu_dist = calculate_hu_moments_dist(cd_i, cd_j)
            if hu_dist >= hu_threshold:
                continue
            if not check_area_difference(cd_i.area, cd_j.area, min_area_ratio):
                continue
            pairs.append((i, j))
    parent = {}
    rank = {}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]  # path compression
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra == rb:
            return
        if rank[ra] < rank[rb]:
            ra, rb = rb, ra
        parent[rb] = ra
        if rank[ra] == rank[rb]:
            rank[ra] += 1

    for i, j in pairs:
        for x in (i, j):
            if x not in parent:
                parent[x] = x
                rank[x] = 0
        union(i, j)

    groups_map = {}
    for i in parent:
        root = find(i)
        if root not in groups_map:
            groups_map[root] = []
        groups_map[root].append(contour_data_list[i])
    groups = list(groups_map.values())

    result = []
    for _, group in enumerate(groups):
        idx_to_remove = set()
        remaining = len(group)
        if remaining <= 1:
            result.append((group, 0.0))
            continue
        for i in range(len(group)):
            if i in idx_to_remove:
                continue
            for j in range(i + 1, len(group)):
                if j in idx_to_remove:
                    continue
                if check_contour_intersection(group[i].contour, group[j].contour):
                    if group[i].compare(group[j]):
                        idx_to_remove.add(j)
                        remaining -= 1
                    else:
                        idx_to_remove.add(i)
                        remaining -= 1
                        break
        filtered_group = [cd for idx, cd in enumerate(group) if idx not in idx_to_remove]
        filtered_smoothness = [cd.smoothness for cd in filtered_group]
        group_similarity = np.std(filtered_smoothness) / np.mean(filtered_smoothness)
        result.append((filtered_group, group_similarity))

    return result
