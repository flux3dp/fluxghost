#!/usr/bin/env python3

import numpy as np

import freeless
import scan_settings


def to_image(buffer_data, img_width, img_height):
    '''
        convert buffer_data into image -> (numpy.ndarray, uint8)
    '''
    int_data = list(buffer_data)
    img_width = scan_settings.img_width
    img_height = scan_settings.img_height

    assert len(int_data) == img_width * img_height, "data length != width * height, %d != %d * %d" % (len(int_data), img_width, img_height)

    image = [int_data[i * img_width: (i + 1) * img_width] for i in range(img_height)]

    return np.array(image, dtype=np.uint8)


class image_to_point_cloud():
    """docstring for image_to_point_cloud"""
    def __init__(self):
        self.reset()

    def reset(self):
        self.points_L = []
        self.fs_L = freeless(scan_settings.laserX_L, scan_settings.laserZ_L)

        self.points_R = []
        self.fs_R = freeless(scan_settings.laserX_R, scan_settings.laserZ_R)

        self.step_counter = 0

    def feed(buffer_O, buffer_L, buffer_R, step):
        img_O = to_image(buffer_O)
        img_L = to_image(buffer_L)
        img_R = to_image(buffer_R)

        indices_L = fs_L.subProcess(img_O, img_L)
        point_L_this = lss_L.img_to_points(img_O, img_L, indices_L, step, 'L', clock=True)
        points_L.extend(point_L_this)

        indices_R = fs_R.subProcess(img_O, img_R)
        point_R_this = lss_R.img_to_points(img_O, img_R, indices_R, step, 'R', clock=True)
        points_R.extend(point_L_this)

        return
