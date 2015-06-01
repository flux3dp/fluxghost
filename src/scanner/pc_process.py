#!/usr/bin/env python3
import struct
from operator import ge, le

import numpy as np


import scan_settings
import _scanner


class pc_process():
    """process point cloud"""
    def __init__():
        pass

    def crop(pc, mode, direction, thres):
        """
            manual cut the point cloud
            mode = 'x', 'y', 'z' ,'r'
            direction = True(>=), False(<=)
        """
        if direction:  # ge = >=, le = <=
            cmp_function = ge
        else:
            cmp_function = le
        cropped_pc = []

        if mode == 'r':
            for p in pc:
                if cmp_function(p[0] ** 2 + p[1] ** 2, thres ** 2):
                    cropped_pc.append(p)
            return cropped_pc

        elif mode == 'x':
            index = 0
        elif mode == 'y':
            index = 1
        elif mode == 'z':
            index = 2
        for p in pc:
            if cmp_function(p[index], thres):
                cropped_pc.append(p)

        return cropped_pc

    def noise_del(file_name):
        pc = _scanner.PointCloudXYZRGBObj()
        pc.load(file_name)
        pc.SOR(50, 0.3)
        return pc
