#!/usr/bin/env python3

import struct
from operator import ge, le


import scan_settings
import _scanner


class pc_process():
    """process point cloud"""
    def __init__(self):
        self.clouds = {}  # clouds that hold all the point cloud data, key:name, value:point cloud

    def upload(self, name, buffer_pc_L, buffer_pc_R=None):
        # upload [name] [point count L] [point count R]
        pass

    def base(self, name):
        self.current_name = name

    def cut(self, pc, mode, direction, thres):
        """
            manually cut the point cloud
            mode = 'x', 'y', 'z' ,'r'
            direction = True(>=), False(<=)
        """
        pc = (pc)
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

    def to_cpp(pc_python):
        pc = _scanner.PointCloudXYZRGBObj()
        for i in pc_python:
            _scanner.push_backPoint(pc, i[0], i[1], i[2], i[3] | (i[4] << 8) | (i[5] << 16))

    def noise_del(self, pc_source):
        """
        pc_source could be a string indcating the file that we want or a pc object
        """
        if type(pc_source) == str:
            pc = _scanner.PointCloudXYZRGBObj()
            pc.load(pc_source)
        else:
            pc = pc_source
        pc.SOR(50, 0.3)
        return pc

    def to_mesh(self):
        pass

if True:
    pass
#
