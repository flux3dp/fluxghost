import logging
from collections import namedtuple

import numpy as np
from scipy import spatial

logger = logging.getLogger('API.CAMERA_CALIBRATION')

# Soft-inlier sigma of the relative term (pattern shape), in remapped image pixels: a point scores
# 0.5 at 1.18 * sigma and min_point_score (0.1) at 2.15 * sigma. Ceiling is the reference point
# spacing, ~390px on bb2 and ~800px on bm2 - past about a third of that a point starts scoring
# against its neighbour's corner instead of its own.
REL_SIGMA = 60
# Sigma of the absolute term: how far the pattern may sit from where rvec/tvec projects it.
# Deliberately loose, the pose prior is only a hint (and is garbage right after a ChArUco
# calibration, where the board pose is wherever the user held the board).
# ponytail: tuning knob, tighten once the frontend default points are verified on every device.
ABS_SIGMA = 300

CornerMatch = namedtuple('CornerMatch', 'points matched ref_index score_detail rel_score abs_score')


def match_projected_points(corners, projected_points, min_rel_score=0.5, min_point_score=0.1):
    """Match detected blob centers against the reference points projected by rvec/tvec.

    Each hypothesis is a (ref_index, candidate corner) pair: the projected pattern is translated
    so projected_points[ref_index] lands on that corner. A hypothesis scores

      relative: soft-inlier score (sigma REL_SIGMA) of the remaining points against the
                translated pattern, i.e. how well the corner constellation matches, and
      absolute: how well the translation itself agrees with the projected pose (sigma ABS_SIGMA).

    Ranking uses relative + absolute, so a trustworthy pose breaks ties between repeated
    patterns; acceptance still uses the relative score alone, so a wrong pose cannot reject
    a pattern that clearly matches.

    Returns a CornerMatch, or None when nothing matched well enough. `points` has points whose
    own score is below min_point_score replaced by the anchor plus their projected offset.
    """
    corners = np.asarray(corners, dtype=float)
    projected_points = np.asarray(projected_points, dtype=float)
    target_counts = len(projected_points)

    if len(corners) < target_counts:
        return None

    corner_tree = spatial.KDTree(corners)
    best_res = None

    for ref_index in range(target_counts):
        for candidate_index in range(len(corners)):
            res = [None] * target_counts
            rel_score = 0
            score_detail = [0] * target_counts
            res[ref_index] = corners[candidate_index]
            score_detail[ref_index] = 1.0
            used_indices = set([candidate_index])
            delta = corners[candidate_index] - projected_points[ref_index]
            abs_score = float(np.exp(-delta.dot(delta) / (2 * ABS_SIGMA * ABS_SIGMA)))
            # Find best match point for target_counts - 1 times, add min dist result for each time
            for i in range(target_counts - 1):
                min_dist_data = None
                # Check for j-th target point distance
                for j in range(target_counts):
                    if res[j] is not None:
                        continue
                    dists, indices = corner_tree.query(projected_points[j] + delta, k=1 + len(used_indices))
                    for dist, idx in zip(dists, indices):
                        if idx not in used_indices:
                            if min_dist_data is None or dist < min_dist_data[0]:
                                min_dist_data = (dist, idx, j)
                            break
                dist, corner_idx, target_idx = min_dist_data
                used_indices.add(corner_idx)
                res[target_idx] = corners[corner_idx]
                point_score = np.exp(-(dist * dist) / (2 * REL_SIGMA * REL_SIGMA))
                score_detail[target_idx] = point_score
                rel_score += point_score
                # Early stop: even all next points are perfect score, total cannot exceed best_res
                if (
                    best_res
                    and rel_score + abs_score + (target_counts - i - 2) < best_res.rel_score + best_res.abs_score
                ):
                    break
            if best_res is None or rel_score + abs_score > best_res.rel_score + best_res.abs_score:
                best_res = CornerMatch(None, np.array(res), ref_index, score_detail, rel_score, abs_score)

    logger.info(
        '[solve_pnp] Score: %.2f relative + %.2f absolute, detail: %s'
        % (best_res.rel_score, best_res.abs_score, best_res.score_detail)
    )

    if best_res.rel_score < min_rel_score:
        logger.info('[solve_pnp] Relative score %.2f is less than threshold.' % best_res.rel_score)

        return None

    points = best_res.matched.copy()

    for i in range(target_counts):
        if best_res.score_detail[i] < min_point_score:
            logger.info(
                '[solve_pnp] Point %d score: %.2f less than threshold, use ref point + offset'
                % (i, best_res.score_detail[i])
            )
            points[i] = best_res.matched[best_res.ref_index] + (
                projected_points[i] - projected_points[best_res.ref_index]
            )

    return best_res._replace(points=points)
