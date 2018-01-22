from datetime import datetime
from getpass import getuser
import logging
import io
import numpy as np
from PIL import Image

import cv2
from math import radians, degrees, cos, sin
from pprint import pprint

from .misc import BinaryUploadHelper, BinaryHelperMixin, OnTextMessageMixin

logger = logging.getLogger("API.CAMERA_CALIBBRATION")

def camera_calibration_api_mixin(cls):
    class CameraCalibrationApi(OnTextMessageMixin, BinaryHelperMixin, cls):

        def __init__(self, *args, **kw):
            super(CameraCalibrationApi, self).__init__(*args, **kw)
            self.cmd_mapping = {
                'upload': [self.cmd_upload_image]
            }

        def cmd_upload_image(self, message):
            def upload_callback(buf):
                img = Image.open(io.BytesIO(buf))
                img_cv = np.array(img);
                result = calc_picture_shape(img_cv)
                self.send_ok(x=result['x'], y=result['y'], angle=result['angle'], size=result['size'])

            file_length = int(message)
            helper = BinaryUploadHelper(int(file_length), upload_callback)
            self.set_binary_helper(helper)
            self.send_json(status="continue")

    def calc_picture_shape(img):
        PI = np.pi

        def calc_it(img):
            gray_image = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY);

            lines = _find_four_main_lines(gray_image)
            angle = _get_angle(lines)
            size = _get_size(lines)
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
            ret = {
                'x': x,
                'y': y,
                'angle': angle,
                'size': size,
            }

            return ret

        # use opencv to find four main lines of calibration image
        # return four lines, each contains [rho, theta]. see HoughLine to know what is rho and theta
        def _find_four_main_lines(img):
            img_blur = cv2.medianBlur(img,5)
            img_threshold = 255 - cv2.adaptiveThreshold(img_blur,255,cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY,11,2)
            
            # another technique to find edge
            # img_edge = cv2.Canny(img, 50, 150, apertureSize = 3)

            image_to_use = img_threshold #img_edge
            raw_lines = cv2.HoughLines(image_to_use, 1, radians(1), 100)

            #make lines = [ [rho, theta], ... ]
            lines = [ x[0] for x in raw_lines ]
            # make (rho >= 0), and (-PI < theta < PI)
            lines = [ [x[0], x[1]] if (x[0] >= 0) else [-x[0], x[1]-PI] for x in lines ]

            # group lines
            deviation = radians(15)
            h_lines = [x for x in lines if (abs(x[1] - PI/2) < deviation)]
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
            return [
                mean_line(lines_top),
                mean_line(lines_bottom),    
                mean_line(lines_left),    
                mean_line(lines_right)
            ]

        # return angle in radian
        def _get_angle(lines):
            [top, bottom, left, right] = lines
            average_angle = (left[1] + right[1] + (top[1] - PI/2) + (bottom[1] - PI/2))/4
            return average_angle

        # return size in pixel
        def _get_size(lines):
            [top, bottom, left, right] = lines
            average_size = ( (bottom[0]-top[0]) + (right[0]-left[0]) )/2
            return average_size

        # return [x, y] in pixel
        def _get_center(lines):
            [top, bottom, left, right] = lines
            
            # this is magic
            def get_intersection(line1, line2):
                r, a = line1
                s, b = line2
                t = (r*cos(a-b) - s)/sin(a-b) 
                x = r*cos(a) - t*sin(a)
                y = r*sin(a) + t*cos(a)
                return [x, y]

            i1 = get_intersection(top, left)
            i2 = get_intersection(top, right)
            i3 = get_intersection(bottom, left)
            i4 = get_intersection(bottom, right)

            center_x = np.mean([ii[0] for ii in [i1, i2, i3, i4] ])
            center_y = np.mean([ii[1] for ii in [i1, i2, i3, i4] ])

            return (center_x, center_y)

        return calc_it(img)

    return CameraCalibrationApi
