import logging
import io
import json
from math import radians, cos, sin
from time import time

import cv2
import numpy as np
from PIL import Image
from scipy import spatial


from fluxghost.utils.fisheye.calibration import (
    calibrate_fisheye,
    calibrate_fisheye_camera,
    distort_points,
    find_chessboard,
    get_remap_img,
    remap_corners,
)
from fluxghost.utils.fisheye.constants import CHESSBOARD, L_PAD, R_PAD, T_PAD, B_PAD
from fluxghost.utils.fisheye.general import pad_image
from fluxghost.utils.fisheye.solve_pnp import solve_pnp
from fluxghost.utils.fisheye.corner_detection import apply_points, find_corners
from fluxghost.utils.fisheye.corner_detection.constants import get_ref_points
from fluxghost.utils.fisheye.charuco.detect import get_calibration_data_from_charuco

from .misc import BinaryUploadHelper, BinaryHelperMixin, OnTextMessageMixin

IS_DEBUGGING = False
logger = logging.getLogger('API.CAMERA_CALIBRATION')


def camera_calibration_api_mixin(cls):
    class CameraCalibrationApi(OnTextMessageMixin, BinaryHelperMixin, cls):
        def __init__(self, *args, **kw):
            super(CameraCalibrationApi, self).__init__(*args, **kw)
            # TODO: add all in one fisheye calibration
            self.cmd_mapping = {
                'upload': [self.cmd_upload_image],
                'calibrate_fisheye': [self.cmd_calibrate_fisheye],
                'detect_charuco': [self.cmd_detect_charuco],
                'start_fisheye_calibration': [self.cmd_start_fisheye_calibration],
                'add_fisheye_calibration_image': [self.cmd_add_fisheye_calibration_image],
                'do_fisheye_calibration': [self.cmd_do_fisheye_calibration],
                'calibrate_chessboard': [self.cmd_calibrate_chessboard],
                'solve_pnp_find_corners': [self.cmd_solve_pnp_find_corners],
                'solve_pnp_calculate': [self.cmd_solve_pnp_calculate],
                'update_data': [self.cmd_update_data],
                'extrinsic_regression': [self.cmd_extrinsic_regression],
                'interrupt': [self.cmd_interrupt],
            }
            self.init_fisheye_params()
            self.init_calibration_params()

        def init_fisheye_params(self):
            self.fisheye_calibrate_heights = []
            self.fisheye_calibrate_imgs = []
            self.k = None
            self.d = None
            self.interrupted = False

        def init_calibration_params(self):
            self.calibration_params = {}

        def cmd_interrupt(self, message):
            self.interrupted = True
            self.send_ok()

        def check_interrupted(self):
            return self.interrupted

        def on_progress(self, progress):
            self.timer = time()
            self.send_json(status='progress', progress=progress)

        def cmd_upload_image(self, message):
            message = message.split(' ')

            def upload_callback(buf):
                img = Image.open(io.BytesIO(buf))
                img_cv = np.array(img)
                result = calc_picture_shape(img_cv)
                if result is None:
                    self.send_json(status='none')
                elif result == 'Fail':
                    self.send_json(status='fail')
                else:
                    self.send_ok(
                        x=result['x'],
                        y=result['y'],
                        angle=result['angle'],
                        width=result['width'],
                        height=result['height'],
                    )

            file_length = int(message[0])
            helper = BinaryUploadHelper(int(file_length), upload_callback)
            self.set_binary_helper(helper)
            self.send_json(status='continue')

        def cmd_start_fisheye_calibration(self, message):
            self.init_fisheye_params()
            self.send_ok()

        def cmd_update_data(self, message):
            data = json.loads(message)
            for key in ['k', 'd', 'rvec', 'tvec', 'rvec_polyfit', 'tvec_polyfit', 'levelingData']:
                if key in data:
                    self.calibration_params[key] = np.array(data[key])
            self.send_ok()

        def cmd_add_fisheye_calibration_image(self, message):
            message = message.split(' ')

            def upload_callback(buf):
                img = Image.open(io.BytesIO(buf))
                img_cv = np.array(img)
                img_cv = cv2.cvtColor(img_cv, cv2.COLOR_RGBA2BGR)
                img_z = float(message[1])
                self.fisheye_calibrate_heights.append(img_z)
                self.fisheye_calibrate_imgs.append(img_cv)
                self.send_ok()

            file_length = int(message[0])
            helper = BinaryUploadHelper(int(file_length), upload_callback)
            self.set_binary_helper(helper)
            self.send_json(status='continue')

        def cmd_do_fisheye_calibration(self, message):
            try:
                ret, k, d, rvecs, tvecs, heights = calibrate_fisheye_camera(
                    self.fisheye_calibrate_imgs, self.fisheye_calibrate_heights, CHESSBOARD, self.on_progress
                )
                if self.check_interrupted():
                    return
                self.k = k
                self.d = d
                rvecs = np.array(rvecs)
                tvecs = np.array(tvecs)
                # difference between chessboard origin and laser origin
                tvecs = tvecs + np.array(([35], [55], [0]))
                rvec_polyfit = np.polyfit(heights, rvecs.reshape(-1, 3), 1)
                tvec_polyfit = np.polyfit(heights, tvecs.reshape(-1, 3), 1)
                rvec_0 = np.dot([0, 1], rvec_polyfit)
                tvec_0 = np.dot([0, 1], tvec_polyfit)
                self.send_ok(
                    ret=ret,
                    k=k.tolist(),
                    d=d.tolist(),
                    rvec=rvec_0.tolist(),
                    tvec=tvec_0.tolist(),
                    rvec_polyfit=rvec_polyfit.tolist(),
                    tvec_polyfit=tvec_polyfit.tolist(),
                )

            except Exception as e:
                if self.check_interrupted():
                    return
                self.send_json(status='fail', reason=str(e))
                raise (e)

        def cmd_calibrate_chessboard(self, message):
            message = message.split(' ')
            file_length = int(message[0])
            height = float(message[1])
            chess_w = int(message[2])
            chess_h = int(message[3])

            def upload_callback(buf):
                img = Image.open(io.BytesIO(buf))
                img_cv = np.array(img)
                img_cv = cv2.cvtColor(img_cv, cv2.COLOR_RGBA2BGR)
                try:
                    calibrate_ret, k, d, rvecs, tvecs, _ = calibrate_fisheye_camera(
                        [img_cv], [height], [chess_w, chess_h], self.on_progress
                    )
                    rvecs = np.array(rvecs)
                    tvecs = np.array(tvecs)
                    remap = pad_image(img_cv)
                    remap = get_remap_img(remap, k, d)
                    objp = np.zeros((chess_w * chess_h, 1, 3), np.float64)
                    objp[:, :, :2] = np.mgrid[0:chess_w, 0:chess_h].T.reshape(-1, 1, 2) * 10
                    objp[:, :, 2] = -height
                    _, ret, corners = find_chessboard(
                        remap, [chess_w, chess_h], 2, do_subpix=True, try_denoise=False, k=k, d=d
                    )
                    projected, _ = cv2.fisheye.projectPoints(objp, rvecs[0], tvecs[0], k, d)
                    projected = remap_corners(projected, k, d).reshape(chess_h, chess_w, 2)
                    corners = np.array(corners).reshape(chess_h, chess_w, 2) if ret else None
                    for i in range(chess_h):
                        for j in range(chess_w):
                            if corners is not None:
                                p = tuple(corners[i][j].astype(int))
                                cv2.circle(remap, p, 0, (0, 0, 255), -1)
                                cv2.circle(remap, p, 3, (0, 0, 255), 1)
                                if i > 0:
                                    cv2.line(remap, p, tuple(corners[i - 1][j].astype(int)), (0, 0, 255))
                                if j > 0:
                                    cv2.line(remap, p, tuple(corners[i][j - 1].astype(int)), (0, 0, 255))
                            p = tuple(projected[i][j].astype(int))
                            cv2.circle(remap, p, 0, (255, 0, 0), -1)
                            cv2.circle(remap, p, 3, (255, 0, 0), 1)
                            if i > 0:
                                cv2.line(remap, p, tuple(projected[i - 1][j].astype(int)), (255, 0, 0))
                            if j > 0:
                                cv2.line(remap, p, tuple(projected[i][j - 1].astype(int)), (255, 0, 0))
                    remap = apply_points(
                        remap,
                        projected,
                        [i * 10 for i in range(chess_w)],
                        [i * 10 for i in range(chess_h)],
                        padding=150,
                    )

                    # difference between chessboard origin and laser origin
                    tvecs = tvecs + np.array(([35], [55], [0]))
                    self.calibration_params['k'] = k
                    self.calibration_params['d'] = d
                    self.calibration_params['rvec'] = rvecs[0]
                    self.calibration_params['tvec'] = tvecs[0]
                    _, array_buffer = cv2.imencode('.jpg', remap)
                    img_bytes = array_buffer.tobytes()
                    self.send_binary(img_bytes)
                    self.send_ok(
                        ret=calibrate_ret, k=k.tolist(), d=d.tolist(), rvec=rvecs[0].tolist(), tvec=tvecs[0].tolist()
                    )
                except Exception as e:
                    if self.check_interrupted():
                        return
                    self.send_json(status='fail', reason=str(e))
                    logger.exception('calibrate chessboard failed')

            helper = BinaryUploadHelper(int(file_length), upload_callback)
            self.set_binary_helper(helper)
            self.send_json(status='continue')

        # solve pnp step 1: given img and dh, find corners, return corners for user to check
        def cmd_solve_pnp_find_corners(self, message):
            if self.calibration_params.get('k', None) is None:
                self.send_json(status='fail', info='NO_DATA', reason='No calibration data found')
                return
            k = self.calibration_params['k']
            d = self.calibration_params['d']
            rvec = self.calibration_params['rvec']
            tvec = self.calibration_params['tvec']
            message = message.split(' ')
            ref_points = json.loads(message[0])
            if isinstance(ref_points, int):
                ref_points = get_ref_points(ref_points)
                logger.warning('Use version ref points is deprecated')
            dh = round(float(message[1]), 2)
            ref_points = np.array([(x, y, -dh) for x, y in ref_points]).reshape(-1, 1, 3)
            file_length = int(message[2])
            interest_area = message[3] if len(message) > 3 else None
            if interest_area:
                interest_area = json.loads(interest_area)

            def upload_callback(buf):
                img = Image.open(io.BytesIO(buf))
                img_cv = np.array(img)
                img_cv = cv2.cvtColor(img_cv, cv2.COLOR_RGBA2BGR)
                remap = pad_image(img_cv)
                remap = get_remap_img(remap, k, d)
                if interest_area:
                    x, y = interest_area['x'], interest_area['y']
                    width, height = interest_area['width'], interest_area['height']
                    interested_img = remap[y : y + height, x : x + width]
                    corners = find_corners(interested_img, 2000, min_distance=100, quality_level=0.01, draw=False)
                    corners = corners + np.array([x, y])
                else:
                    corners = find_corners(remap, 2000, min_distance=100, quality_level=0.01, draw=False)
                projected_points, _ = cv2.fisheye.projectPoints(ref_points, rvec, tvec, k, d)
                projected_points = remap_corners(projected_points, k, d).reshape(-1, 2)

                if IS_DEBUGGING:
                    remap_copy = remap.copy()
                    if interest_area:
                        cv2.rectangle(remap_copy, (x, y), (x + width, y + height), (0, 0, 255), 1)
                    for c in corners:
                        cv2.circle(remap_copy, tuple(c.astype(int)), 0, (0, 0, 255), -1)
                        cv2.circle(remap_copy, tuple(c.astype(int)), 3, (0, 0, 255), 1)
                    for p in projected_points:
                        cv2.circle(remap_copy, tuple(p.astype(int)), 0, (255, 0, 0), -1)
                        cv2.circle(remap_copy, tuple(p.astype(int)), 3, (255, 0, 0), 1)

                if len(corners) > len(projected_points):
                    corner_tree = spatial.KDTree(corners)
                    _, candidates_indice = corner_tree.query(projected_points[0], k=len(corners))
                    best_res = None
                    for index in candidates_indice:
                        res = [corners[index]]
                        used_indices = set([index])
                        total_dist = 0
                        delta = corners[index] - projected_points[0]
                        for i in range(1, len(projected_points)):
                            desire_point = projected_points[i] + delta
                            dists, indices = corner_tree.query(desire_point, k=len(projected_points))
                            for j in range(len(indices)):
                                if indices[j] not in used_indices:
                                    used_indices.add(indices[j])
                                    res.append(corners[indices[j]])
                                    total_dist += dists[j]
                                    break
                                if best_res and total_dist > best_res[1]:
                                    break
                        if best_res is None or total_dist < best_res[1]:
                            best_res = (res, total_dist)
                    result_img_points = np.array(best_res[0])
                else:
                    logger.info('corners lens: {} is less than projected_points, use projected_points'.format(len(corners)))
                    result_img_points = projected_points

                self.send_ok(points=result_img_points.tolist())
                _, array_buffer = cv2.imencode('.jpg', remap)
                img_bytes = array_buffer.tobytes()
                self.send_binary(img_bytes)
                if IS_DEBUGGING:
                    for p in result_img_points:
                        cv2.circle(remap_copy, tuple(p.astype(int)), 0, (255, 255, 0), -1)
                        cv2.circle(remap_copy, tuple(p.astype(int)), 3, (255, 255, 0), 1)
                    cv2.imwrite('solve-pnp-corner.png', remap_copy)

            helper = BinaryUploadHelper(int(file_length), upload_callback)
            self.set_binary_helper(helper)
            self.send_json(status='continue')

        def cmd_solve_pnp_calculate(self, message):
            if self.calibration_params.get('k', None) is None:
                self.send_json(status='fail', info='NO_DATA', reason='No calibration data found')
            k = self.calibration_params['k']
            d = self.calibration_params['d']
            message = message.split(' ')
            ref_points = json.loads(message[0])
            if isinstance(ref_points, int):
                ref_points = get_ref_points(ref_points)
                logger.warning('Use version ref points is deprecated')
            dh = round(float(message[1]), 2)
            objpoints = np.array([(x, y, -dh) for x, y in ref_points]).reshape(-1, 1, 3)
            imgpoints = np.array(json.loads(message[2]))
            distorted = distort_points(imgpoints, k, d)

            try:
                ret, new_rvec, new_tvec = solve_pnp(objpoints, distorted.reshape(-1, 1, 2), k, d)
                if not ret:
                    self.send_json(status='fail', reason='solve pnp failed')
                    return
                self.calibration_params['rvec'] = new_rvec
                self.calibration_params['tvec'] = new_tvec
                self.send_ok(rvec=new_rvec.tolist(), tvec=new_tvec.tolist())
            except Exception as e:
                self.send_json(status='fail', reason='solve pnp failed' + str(e))

        def cmd_extrinsic_regression(self, message):
            message = message.split(' ')
            rvecs = np.array(json.loads(message[0]))
            tvecs = np.array(json.loads(message[1]))
            heights = np.array(json.loads(message[2]))
            rvec_polyfit = np.polyfit(heights, rvecs.reshape(-1, 3), 1)
            tvec_polyfit = np.polyfit(heights, tvecs.reshape(-1, 3), 1)
            self.send_ok(rvec_polyfit=rvec_polyfit.tolist(), tvec_polyfit=tvec_polyfit.tolist())

        def cmd_detect_charuco(self, message):
            message = message.split(' ')
            file_length = int(message[0])
            squares_x = int(message[1])
            squares_y = int(message[2])

            def upload_callback(buf):
                img = Image.open(io.BytesIO(buf))
                img_cv = np.array(img)
                img_cv = cv2.cvtColor(img_cv, cv2.COLOR_RGBA2BGR)
                res = get_calibration_data_from_charuco(img_cv, squares_x, squares_y)
                if res is None:
                    self.send_json(status='fail', reason='Failed to detect image.')
                    return
                imgp, objp = res
                self.send_ok(imgp=imgp.tolist(), objp=objp.tolist())

            helper = BinaryUploadHelper(int(file_length), upload_callback)
            self.set_binary_helper(helper)
            self.send_json(status='continue')

        def cmd_calibrate_fisheye(self, message):
            message = message.split(' ')
            objpoints = [np.array(objp).reshape(1, -1, 3).astype(np.float32) for objp in json.loads(message[0])]
            imgpoints = [np.array(imgp).reshape(1, -1, 2).astype(np.float32) for imgp in json.loads(message[1])]
            img_size = json.loads(message[2])
            indices = list(range(len(objpoints)))

            # apply padding
            # TODO: support different padding value?
            for i in range(len(imgpoints)):
                imgpoints[i] = imgpoints[i] + np.array([L_PAD, T_PAD]).astype(np.float32)
            img_size = (img_size[0] + L_PAD + R_PAD, img_size[1] + T_PAD + B_PAD)

            try:
                ret, k, d, rvecs, tvecs, indices = calibrate_fisheye(objpoints, imgpoints, indices, img_size)
                self.calibration_params['k'] = k
                self.calibration_params['d'] = d
                self.calibration_params['rvec'] = rvecs[0]
                self.calibration_params['tvec'] = tvecs[0]
                self.send_ok(
                    ret=ret,
                    k=k.tolist(),
                    d=d.tolist(),
                    rvecs=rvecs[0].tolist(),
                    tvecs=tvecs[0].tolist(),
                    indices=indices,
                )
            except Exception as e:
                self.send_json(status='fail', reason=str(e))
                raise (e)


    def calc_picture_shape(img):
        PI = np.pi

        def calc_it(img):
            gray_image = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

            lines = _find_four_main_lines(gray_image)

            if lines is None:
                return None
            elif lines == 'Fail':
                return 'Fail'

            angle = _get_angle(lines)
            [width, height] = _get_size(lines)
            [x, y] = _get_center(lines)

            # output_img = np.copy(img)
            # for rho, theta in lines:
            #     a = cos(theta)
            #     b = sin(theta)
            #     x0 = a*rho
            #     y0 = b*rho
            #     x1 = int(x0 + 1000*(-b))
            #     y1 = int(y0 + 1000*(a))
            #     x2 = int(x0 - 1000*(-b))
            #     y2 = int(y0 - 1000*(a))

            #     cv2.line(output_img,(x1,y1),(x2,y2),255,1)

            # cv2.imwrite('houghlines.jpg',output_img)
            ret = {'x': x, 'y': y, 'angle': angle, 'width': float(width), 'height': float(height)}

            return ret

        # use opencv to find four main lines of calibration image
        # return four lines, each contains [rho, theta]. see HoughLine to know what is rho and theta
        def _find_four_main_lines(img):
            img_blur = cv2.medianBlur(img, 5)
            img_threshold = 255 - cv2.adaptiveThreshold(
                img_blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
            )

            # another technique to find edge
            # img_edge = cv2.Canny(img, 50, 150, apertureSize = 3)

            image_to_use = img_threshold  # img_edge
            raw_lines = cv2.HoughLines(image_to_use, 1, radians(1), 100)

            if raw_lines is None:
                return None
            elif np.isnan(raw_lines).tolist().count([True, True]) > 0:
                return 'Fail'

            # make lines = [ [rho, theta], ... ]
            lines = [x[0] for x in raw_lines]
            # make (rho >= 0), and (-PI < theta < PI)
            lines = [[x[0], x[1]] if (x[0] >= 0) else [-x[0], x[1] - PI] for x in lines]

            # group lines
            deviation = radians(15)
            h_lines = [x for x in lines if (abs(x[1] - PI / 2) < deviation)]
            v_lines = [x for x in lines if (abs(x[1] - 0) < deviation)]

            # np.mean() is average()
            # use average as watershed to seperate top, bottom, left, right lines
            h_average_rho = np.mean([x[0] for x in h_lines])
            v_average_rho = np.mean([x[0] for x in v_lines])

            # get four lines
            lines_top = [x for x in h_lines if (x[0] < h_average_rho)]
            lines_bottom = [x for x in h_lines if (x[0] > h_average_rho)]
            lines_left = [x for x in v_lines if (x[0] < v_average_rho)]
            lines_right = [x for x in v_lines if (x[0] > v_average_rho)]

            def mean_line(line):
                rho = np.mean([x[0] for x in line])
                theta = np.mean([x[1] for x in line])
                return [rho, theta]

            return [mean_line(lines_top), mean_line(lines_bottom), mean_line(lines_left), mean_line(lines_right)]

        # return angle in radian
        def _get_angle(lines):
            [top, bottom, left, right] = lines
            average_angle = (left[1] + right[1] + (top[1] - PI / 2) + (bottom[1] - PI / 2)) / 4
            return average_angle

        # return size in pixel
        def _get_size(lines):
            [top, bottom, left, right] = lines
            width = right[0] - left[0]
            height = bottom[0] - top[0]
            return (width, height)

        # return [x, y] in pixel
        def _get_center(lines):
            [top, bottom, left, right] = lines

            # this is magic
            def get_intersection(line1, line2):
                r, a = line1
                s, b = line2
                t = (r * cos(a - b) - s) / sin(a - b)
                x = r * cos(a) - t * sin(a)
                y = r * sin(a) + t * cos(a)
                return [x, y]

            i1 = get_intersection(top, left)
            i2 = get_intersection(top, right)
            i3 = get_intersection(bottom, left)
            i4 = get_intersection(bottom, right)

            center_x = np.mean([ii[0] for ii in [i1, i2, i3, i4]])
            center_y = np.mean([ii[1] for ii in [i1, i2, i3, i4]])

            return (center_x, center_y)

        return calc_it(img)

    return CameraCalibrationApi
