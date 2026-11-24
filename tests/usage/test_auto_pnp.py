"""Automatic solve-PnP mark matching (fluxghost/utils/camera/auto_pnp.py).

Fixture: blobs detected in raw photos of one fbm2 after the calibration engraving, one list per exposure, with
the 16 mark positions that were confirmed by warping the photo through the preview code.
"""

import json
import os
import unittest

import cv2
import numpy as np

from fluxghost.utils.camera.auto_pnp import (
    HIGH_RESIDUAL,
    NOT_ENOUGH_MARKS,
    detect_marks,
    gate,
    match_grid,
    match_marks,
    merge_exposures,
    undistort_centers,
)
from tests.usage._harness import WS, Server

FIXTURE_DIR = os.path.join(os.path.dirname(__file__), 'fixtures', 'auto_pnp')
FIXTURE = os.path.join(FIXTURE_DIR, 'fbm2_unit2_blobs.json')
PHOTO = os.path.join(FIXTURE_DIR, 'fbm2_unit2_exp75.jpg')  # the exposure-75 photo the '75' blob list came from


class TestMatchGridOnPhotos(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(FIXTURE) as f:
            cls.data = json.load(f)
        cls.k, cls.d = np.array(cls.data['k']), np.array(cls.data['d'])
        cls.bed = np.array(cls.data['ref_points'])
        cls.marks = np.array(cls.data['marks'])

    def run_match(self, exposures):
        blobs = merge_exposures([self.data['exposures'][e] for e in exposures])
        raw = np.array([b[:2] for b in blobs])
        assign, rms = match_grid(undistort_centers(raw, self.k, self.d), self.bed)
        # the mark each grid position really is, as a blob index (-1 when this photo does not show it)
        dist = np.linalg.norm(self.marks[:, None] - raw[None], axis=2)
        truth = np.where(dist.min(axis=1) < 3, dist.argmin(axis=1), -1)
        return assign, truth, rms

    def test_all_marks_from_one_good_exposure(self):
        assign, truth, rms = self.run_match(['75'])
        np.testing.assert_array_equal(assign, truth)
        self.assertTrue((assign >= 0).all())
        self.assertLess(rms, 1.0)

    def test_bracket_gives_the_same_answer(self):
        assign, truth, _ = self.run_match(['75', '200'])
        np.testing.assert_array_equal(assign, truth)

    def test_never_assigns_a_wrong_blob_when_most_marks_show(self):
        for exposure in ('50', '100', '150'):
            with self.subTest(exposure=exposure):
                assign, truth, _ = self.run_match([exposure])
                self.assertGreaterEqual((truth >= 0).sum(), 11)
                found = assign >= 0
                np.testing.assert_array_equal(assign[found], truth[found])

    def with_covered_marks(self, exposures, covered, strays_mm):
        """Blobs of the photos with some marks removed and blobs added at mm offsets from them."""
        blobs = merge_exposures([self.data['exposures'][e] for e in exposures])
        raw = np.array([b[:2] for b in blobs])
        keep = np.linalg.norm(raw[:, None] - self.marks[covered][None], axis=2).min(axis=1) > 3
        px_per_mm = np.linalg.norm(self.marks[6] - self.marks[5]) / 100
        strays = [self.marks[i] + np.array(offset) * px_per_mm for i, offset in strays_mm]
        return undistort_centers(np.vstack([raw[keep], *strays]), self.k, self.d)

    def assert_only_real_marks(self, und, covered):
        assign, rms = match_grid(und, self.bed)
        self.assertEqual((assign >= 0).sum(), 16 - len(covered))
        self.assertTrue((assign[covered] == -1).all())
        self.assertLess(rms, 0.75)

    def test_stray_next_to_a_covered_mark_is_not_counted(self):
        # seen on hardware: two marks covered by a board, and a blob on the board 7 mm from one of them was
        # taken for it (15/16, rms 3.5 mm). The count must say what is really there.
        self.assert_only_real_marks(self.with_covered_marks(['75'], [5, 10], [(5, (7, 0))]), [5, 10])

    def test_strays_from_many_exposures_do_not_shift_the_grid(self):
        # same board after the second exposure round: more strays near the covered marks, and the strays of
        # seven exposures crowd the seeds. A grid shifted by one row then fitted 10 blobs perfectly and won.
        strays = [(5, (7, 0)), (5, (-9, 8)), (10, (-5, 6)), (10, (11, -3))]
        self.assert_only_real_marks(self.with_covered_marks(list(self.data['exposures']), [5, 10], strays), [5, 10])

    def marks_result(self, exposures):
        lists = []
        for e in exposures:
            blobs = self.data['exposures'][e]
            und = undistort_centers(np.array([b[:2] for b in blobs]), self.k, self.d)
            lists.append([[x, y, b[2], b[3]] for (x, y), b in zip(und.tolist(), blobs)])
        return match_marks(lists, self.data['ref_points'])

    def test_match_marks_accepts_a_full_set(self):
        res = self.marks_result(['75', '200'])
        self.assertIsNone(res['reason'])
        self.assertEqual(res['matched'], 16)
        expected = undistort_centers(self.marks, self.k, self.d)
        np.testing.assert_allclose(np.array(res['points']), expected, atol=1.0)

    def test_match_marks_rejects_an_overexposed_photo(self):
        res = self.marks_result(['350'])
        self.assertEqual(res['reason'], NOT_ENOUGH_MARKS)
        self.assertIn(None, res['points'])

    def test_match_marks_with_no_blobs(self):
        res = match_marks([[]], self.data['ref_points'])
        self.assertEqual((res['reason'], res['matched'], res['rms']), (NOT_ENOUGH_MARKS, 0, None))


class TestDetectMarks(unittest.TestCase):
    def test_finds_every_mark_in_the_photo(self):
        with open(FIXTURE) as f:
            data = json.load(f)
        k, d = np.array(data['k']), np.array(data['d'])
        blobs = np.array(detect_marks(cv2.imread(PHOTO), k, d))
        self.assertEqual(blobs.shape[1], 4)
        expected = undistort_centers(np.array(data['marks']), k, d)
        nearest = np.linalg.norm(expected[:, None] - blobs[None, :, :2], axis=2).min(axis=1)
        self.assertLess(nearest.max(), 1.0)
        self.assertLess(len(blobs), 60)  # a clean sheet gives the marks plus a few strays, not hundreds

    def test_pinhole_camera_is_not_padded_and_uses_the_pinhole_model(self):
        # k / d of one fhx2rf wide-angle camera (pinhole); the photo is remapped without padding
        k = np.array([[1177.873, 0, 1620.083], [0, 1175.157, 1190.263], [0, 0, 1]])
        d = np.array([[0, -0.010651, -0.000986, -0.000513, -0.000817]])
        und = np.array([[400.0, 300.0], [1620.0, 1190.0], [2436.9, 1790.6], [3124.6, 2297.2]])
        normalized = cv2.undistortPoints(und.reshape(-1, 1, 2), k, None)
        raw, _ = cv2.projectPoints(cv2.convertPointsToHomogeneous(normalized), np.zeros(3), np.zeros(3), k, d)
        np.testing.assert_allclose(undistort_centers(raw.reshape(-1, 2), k, d, is_fisheye=False), und, atol=0.05)

    def test_blank_photo(self):
        self.assertEqual(detect_marks(np.full((240, 320, 3), 200, np.uint8), np.eye(3), np.zeros((4, 1))), [])


class TestAutoPnpWebsocket(unittest.TestCase):
    """The two commands over /ws/camera-calibration, the way Beam Studio calls them."""

    @classmethod
    def setUpClass(cls):
        cls.server = Server()
        with open(FIXTURE) as f:
            cls.data = json.load(f)

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()

    def reply(self, ws):
        return ws.json_until(lambda m: m.get('status') in ('ok', 'fail', 'error', 'continue'))

    def test_detect_then_match(self):
        ws = WS(self.server.port, '/ws/camera-calibration', timeout=60)
        try:
            ws.send('update_data ' + json.dumps({'k': self.data['k'], 'd': self.data['d']}))
            self.assertEqual(self.reply(ws)['status'], 'ok')
            with open(PHOTO, 'rb') as f:
                photo = f.read()
            ws.send('auto_pnp_detect %d' % len(photo))
            self.assertEqual(self.reply(ws)['status'], 'continue')
            ws.send(photo, opcode=2)
            detected = self.reply(ws)
            self.assertEqual(detected['status'], 'ok')
            ws.send(
                'auto_pnp_match ' + json.dumps({'ref_points': self.data['ref_points'], 'blobs': [detected['blobs']]})
            )
            matched = self.reply(ws)
            self.assertEqual((matched['status'], matched['matched']), ('ok', 16))
            self.assertEqual(len(matched['points']), 16)
            # a tighter limit from the caller: a fail that still carries every point
            ws.send(
                'auto_pnp_match '
                + json.dumps({'ref_points': self.data['ref_points'], 'blobs': [detected['blobs']], 'r_max': 0.01})
            )
            tight = self.reply(ws)
            self.assertEqual((tight['status'], tight['reason']), ('fail', HIGH_RESIDUAL))
            self.assertEqual(tight['points'], matched['points'])
            # too few blobs: a fail with the reason, not an error
            ws.send(
                'auto_pnp_match '
                + json.dumps({'ref_points': self.data['ref_points'], 'blobs': [detected['blobs'][:5]]})
            )
            failed = self.reply(ws)
            self.assertEqual((failed['status'], failed['reason']), ('fail', NOT_ENOUGH_MARKS))
            # a fail carries the points too (all of them after HIGH_RESIDUAL), None for a missing mark
            self.assertEqual(len(failed['points']), 16)
            self.assertIn(None, failed['points'])
        finally:
            ws.close()

    def test_detect_follows_is_fisheye_from_update_data(self):
        ws = WS(self.server.port, '/ws/camera-calibration', timeout=60)
        try:
            ws.send('update_data ' + json.dumps({'k': self.data['k'], 'd': self.data['d'], 'is_fisheye': False}))
            self.assertEqual(self.reply(ws)['status'], 'ok')
            with open(PHOTO, 'rb') as f:
                photo = f.read()
            ws.send('auto_pnp_detect %d' % len(photo))
            self.assertEqual(self.reply(ws)['status'], 'continue')
            ws.send(photo, opcode=2)
            blobs = np.array(self.reply(ws)['blobs'])[:, :2]
        finally:
            ws.close()
        k, d = np.array(self.data['k']), np.array(self.data['d'])
        pinhole = np.array(detect_marks(cv2.imread(PHOTO), k, d, is_fisheye=False))[:, :2]
        nearest = np.linalg.norm(blobs[:, None] - pinhole[None], axis=2).min(axis=1)
        self.assertLess(np.median(nearest), 0.5)

    def test_detect_needs_calibration_data(self):
        ws = WS(self.server.port, '/ws/camera-calibration')
        try:
            ws.send('auto_pnp_detect 10')
            self.assertEqual(self.reply(ws).get('info'), 'NO_DATA')
        finally:
            ws.close()


class TestFaintMarks(unittest.TestCase):
    """A unit whose bottom-left marks are too faint for the detector at every exposure (lens flare)."""

    @classmethod
    def setUpClass(cls):
        with open(os.path.join(FIXTURE_DIR, 'fbm2_unit3_faint_marks.json')) as f:
            cls.data = json.load(f)

    def run_match(self, with_weak):
        exposures = list(self.data['blobs'])
        weak = [self.data['weak'][e] for e in exposures] if with_weak else None
        return match_marks([self.data['blobs'][e] for e in exposures], self.data['ref_points'], weak)

    def test_two_marks_missing_without_the_weak_candidates(self):
        res = self.run_match(with_weak=False)
        self.assertEqual((res['reason'], res['matched'], res['filled']), (NOT_ENOUGH_MARKS, 14, 0))
        self.assertEqual([i for i, p in enumerate(res['points']) if p is None], [8, 12])  # (30, 150) and (30, 210)

    def test_weak_candidates_next_to_the_predicted_positions_complete_the_set(self):
        res = self.run_match(with_weak=True)
        self.assertEqual((res['reason'], res['matched'], res['filled']), (None, 16, 2))
        self.assertLess(res['rms'], 0.75)

    def test_weak_candidates_are_not_used_with_too_few_marks(self):
        # one overexposed photo shows half the marks; hundreds of weak blobs must not fill in the rest
        res = match_marks([self.data['blobs']['200']], self.data['ref_points'], [self.data['weak']['200']])
        self.assertEqual((res['reason'], res['filled']), (NOT_ENOUGH_MARKS, 0))


class TestNestedRectangles(unittest.TestCase):
    """The 8-mark layouts (fbb2 / fhx2rf laser head, Ador): two concentric rectangles, not a lattice."""

    @classmethod
    def setUpClass(cls):
        with open(os.path.join(FIXTURE_DIR, 'nested_rectangles_8_marks.json')) as f:
            cls.cases = json.load(f)['cases']

    def wrong(self, res, case):
        pairs = zip(res['points'], case['marks'])
        return [p for p, m in pairs if p is not None and np.hypot(p[0] - m[0], p[1] - m[1]) > 2]

    def test_finds_the_eight_marks_among_old_marks(self):
        for case in self.cases:
            with self.subTest(case['name']):
                res = match_marks([case['blobs']], case['ref_points'])
                self.assertEqual((res['matched'], res['reason']), (8, None))
                self.assertLess(res['rms'], 0.2)
                self.assertEqual(self.wrong(res, case), [])

    def test_an_old_mark_never_stands_in_for_a_missing_one(self):
        for case in self.cases:
            for hidden in case['marks']:
                with self.subTest(case['name'], hidden=hidden):
                    blobs = [b for b in case['blobs'] if np.hypot(b[0] - hidden[0], b[1] - hidden[1]) > 8]
                    res = match_marks([blobs], case['ref_points'])
                    self.assertEqual((res['matched'], res['reason']), (7, NOT_ENOUGH_MARKS))
                    self.assertEqual(self.wrong(res, case), [])

    def test_an_old_pattern_of_other_proportions_is_not_taken(self):
        # seen on hardware: the old 120 x 80 pattern fitted the 120 x 120 reference with 0.05 mm of residual,
        # a homography absorbs the stretch, and the preview at that height was wrong
        with open(os.path.join(FIXTURE_DIR, 'nested_rectangles_8_marks.json')) as f:
            case = json.load(f)['other_pattern']
        res = match_marks([case['blobs']], case['ref_points'], r_max=0.2)
        self.assertEqual((res['matched'], res['reason']), (8, None))
        self.assertEqual(self.wrong(res, case), [])
        # with a real mark gone nothing may be accepted: an old mark 4 mm away can take its place, and the
        # tighter limit the 8-mark callers pass is what catches that
        for hidden in case['marks']:
            with self.subTest(hidden=hidden):
                blobs = [b for b in case['blobs'] if np.hypot(b[0] - hidden[0], b[1] - hidden[1]) > 8]
                self.assertIsNotNone(match_marks([blobs], case['ref_points'], r_max=0.2)['reason'])

    def test_search_does_not_stop_at_a_fit_over_the_callers_limit(self):
        # found in review: in this blob order a hypothesis with a stray in a mark's place (0.72 mm) comes up
        # before the right one (0.07 mm), and the search used to stop at anything under the default 1.0 mm
        with open(os.path.join(FIXTURE_DIR, 'nested_rectangles_8_marks.json')) as f:
            case = json.load(f)['other_pattern']
        blobs = [[b[0], b[1], b[2], 100.0] for b in case['blobs']]
        blobs = [blobs[i] for i in np.random.default_rng(1).permutation(len(blobs))]
        res = match_marks([blobs], case['ref_points'], r_max=0.2)
        self.assertEqual((res['matched'], res['reason']), (8, None))
        self.assertLess(res['rms'], 0.1)
        self.assertEqual(self.wrong(res, case), [])

    def test_layout_without_a_rectangle_is_not_matched(self):
        res = match_marks([self.cases[0]['blobs']], [[0, 0], [10, 0], [20, 5], [0, 30]])
        self.assertEqual((res['matched'], res['reason']), (0, NOT_ENOUGH_MARKS))


class TestGate(unittest.TestCase):
    def test_gate(self):
        self.assertIsNone(gate(16, 16, 0.5))
        self.assertEqual(gate(15, 16, 0.5), NOT_ENOUGH_MARKS)
        self.assertEqual(gate(16, 16, 6.4), HIGH_RESIDUAL)
        # the caller's limit replaces the default
        self.assertEqual(gate(8, 8, 0.5, r_max=0.2), HIGH_RESIDUAL)
        self.assertIsNone(gate(8, 8, 0.1, r_max=0.2))
        # a missing mark is the more useful thing to tell the user, so it wins
        self.assertEqual(gate(7, 16, 6.4), NOT_ENOUGH_MARKS)
        self.assertEqual(gate(0, 16, float('inf')), NOT_ENOUGH_MARKS)


class TestMatchGridSynthetic(unittest.TestCase):
    def test_grid_similar_to_its_transpose_stays_upright(self):
        # fbb2 wide-angle spacings: 120/180/120 across, 80/120/80 down. Rotated by 90 degrees the grid has the
        # same shape, and without the upright check that assignment fitted real photos better than the true one.
        bed = np.array([(x, y) for y in (40, 120, 240, 320) for x in (90, 210, 390, 510)], float)
        view = np.array([[2.4, 0.5, 300], [0.05, 1.5, 250], [0.0, 0.0009, 1]])  # strong keystone, like a lid camera
        img = cv2.perspectiveTransform(bed.reshape(-1, 1, 2), view).reshape(-1, 2)
        strays = np.array([(150.0, 180.0), (1900.0, 1400.0), (1000.0, 60.0)])
        order = np.random.default_rng(0).permutation(len(img) + len(strays))
        und = np.vstack([img, strays])[order]
        assign, rms = match_grid(und, bed)
        np.testing.assert_array_equal(order[assign], np.arange(16))
        self.assertLess(rms, 0.01)


class TestMergeExposures(unittest.TestCase):
    def test_keeps_each_mark_from_its_best_contrast_exposure(self):
        dark = [[100.0, 100.0, 10.0, 80.0], [300.0, 100.0, 10.0, 20.0]]
        bright = [[101.0, 100.5, 10.0, 30.0], [300.5, 100.0, 10.0, 90.0], [500.0, 100.0, 10.0, 40.0]]
        merged = merge_exposures([dark, bright])
        self.assertEqual(sorted(m[:2] for m in merged), [[100.0, 100.0], [300.5, 100.0], [500.0, 100.0]])


if __name__ == '__main__':
    unittest.main()
