# !/usr/bin/env python3

from io import BytesIO
import logging
import sys
import os


from .base import WebSocketBase, WebsocketBinaryHelperMixin, \
    BinaryUploadHelper, ST_NORMAL, SIMULATE, OnTextMessageMixin
from fluxclient.printer.stl_slicer import StlSlicer

logger = logging.getLogger("WS.slicing")


class Websocket3DSlicing(OnTextMessageMixin, WebsocketBinaryHelperMixin, WebSocketBase):
    """
    This websocket is use to slicing stl model
    """
    POOL_TIME = 30.0

    def __init__(self, *args):
        WebSocketBase.__init__(self, *args)
        logger.info("Using StlSlicer()")
        if "slic3r" in os.environ:
            self.m_stl_slicer = StlSlicer(os.environ["slic3r"])
        else:
            self.m_stl_slicer = StlSlicer("../Slic3r/slic3r.pl")

        self.cmd_mapping = {
            'upload': [self.begin_recv_stl, 'upload'],
            'upload_image': [self.begin_recv_stl, 'upload_image'],
            'set': [self.set],
            'go': [self.gcode_generate],
            'delete': [self.delete],
            'set_params': [self.set_params],
            'advanced_setting': [self.advanced_setting],
            'get_path': [self.get_path],
            'duplicate': [self.duplicate],
            'meta_option': [self.meta_option],
            'begin_slicing': [self.begin_slicing],
            'end_slicing': [self.end_slicing],
            'report_slicing': [self.report_slicing],
            'get_result': [self.get_result]

        }
        self.ext_metadata = {}

    def begin_recv_stl(self, params, flag):
        if flag == 'upload':
            name, file_length = params.split()
        elif flag == 'upload_image':
            name = ''
            file_length = params
        if int(file_length) == 0:
            self.send_error('empty file!')
            # self.send_continue()
            # self.send_ok()
        else:
            helper = BinaryUploadHelper(int(file_length), self.end_recv_stl, name, flag)
            self.set_binary_helper(helper)
            self.send_continue()

    def end_recv_stl(self, buf, *args):
        if args[1] == 'upload':
            self.m_stl_slicer.upload(args[0], buf)
        elif args[1] == 'upload_image':
            self.m_stl_slicer.upload_image(buf)
        self.send_ok()

    def duplicate(self, params):
        name_in, name_out = params.split()
        flag = self.m_stl_slicer.duplicate(name_in, name_out)
        if flag:
            self.send_ok()
        else:
            self.send_error('{} not exist'.format(name_in))

    def set(self, params):
        params = params.split()
        assert len(params) == 10, 'wrong number of parameters %d' % len(params)
        name = params[0]
        position_x = float(params[1])
        position_y = float(params[2])
        position_z = float(params[3])
        rotation_x = float(params[4])
        rotation_y = float(params[5])
        rotation_z = float(params[6])
        scale_x = float(params[7])
        scale_y = float(params[8])
        scale_z = float(params[9])
        self.m_stl_slicer.set(name, [position_x, position_y, position_z, rotation_x, rotation_y, rotation_z, scale_x, scale_y, scale_z])

        self.send_ok()

    def set_params(self, params):
        key, value = params.split()
        if self.m_stl_slicer.set_params(key, value):  # will check if key is valid
            self.send_ok()
        else:
            self.send_error('wrong parameter: %s' % key)

    def advanced_setting(self, params):
        lines = params.split('\n')
        bad_lines = self.m_stl_slicer.advanced_setting(lines)
        if bad_lines != []:
            for line_num, err_msg in bad_lines:
                self.send_error('line %d: %s' % (line_num, err_msg))
                logger.debug('line %d: %s' % (line_num, err_msg))
        self.send_ok()

    def gcode_generate(self, params):
        names = params.split()
        if names[-1] == '-g':
            output_type = '-g'
            names = names[:-1]
        elif names[-1] == '-f':
            output_type = '-f'
            names = names[:-1]
        else:
            output_type = '-f'
        output, metadata = self.m_stl_slicer.gcode_generate(names, self, output_type)
        # self.send_progress('finishing', 1.0)
        if output:
            self.send_text('{"status": "complete", "length": %d, "time": %.3f, "filament_length": %.2f}' % (len(output), metadata[0], metadata[1]))
            self.send_binary(output)
            logger.debug('slicing finish')
        else:
            self.send_error(metadata)
            logger.debug('slicing fail')

    def begin_slicing(self, params):
        names = params.split()
        if names[-1] == '-g':
            output_type = '-g'
            names = names[:-1]
        elif names[-1] == '-f':
            output_type = '-f'
            names = names[:-1]
        else:
            output_type = '-f'
        self.m_stl_slicer.begin_slicing(names, self, output_type)
        self.send_ok()

    def end_slicing(self, *args):
        self.m_stl_slicer.end_slicing()
        self.send_ok()

    def report_slicing(self, *args):
        for m in self.m_stl_slicer.report_slicing():
            self.send_text(m)
        self.send_ok()

    def get_result(self, *args):
        self.send_ok(str(len(self.m_stl_slicer.output)))
        self.send_binary(self.m_stl_slicer.output)

    def get_path(self, *args):
        path = self.m_stl_slicer.get_path()
        if path:
            self.send_text(path)
        else:
            self.send_error('no path data to send')

    def delete(self, params):
        name = params.rstrip()
        flag, message = self.m_stl_slicer.delete(name)
        if flag:
            self.send_ok()
        else:
            self.send_error(message)

    def meta_option(self, params):
        key, value = params.split()
        self.m_stl_slicer.ext_metadata[key] = value
        self.send_ok()
