# !/usr/bin/env python3

import logging
import sys

from .base import WebSocketBase, WebsocketBinaryHelperMixin, \
    BinaryUploadHelper, ST_NORMAL, OnTextMessageMixin
from fluxclient.laser.laser_svg import LaserSvg

logger = logging.getLogger("WS.Laser Svg")

MODE_PRESET = "preset"
MODE_MANUALLY = "manually"


class WebsocketLaserSvgParser(OnTextMessageMixin, WebsocketBinaryHelperMixin, WebSocketBase):
    _m_laser_svg = None

    def __init__(self, *args):
        super(WebsocketLaserSvgParser, self).__init__(*args)
        self.cmd_mapping = {
            'upload': [self.begin_recv_svg, 'upload', None],
            'get': [self.get],
            'compute': [self.compute],
            'go': [self.go],
            'set_params': [self.set_params],
            'meta_option': [self.meta_option]
        }

    @property
    def m_laser_svg(self):
        if self._m_laser_svg is None:
            self._m_laser_svg = LaserSvg()
        return self._m_laser_svg

    def begin_recv_svg(self, message, flag, *args):
        self.POOL_TIME_ = self.POOL_TIME
        self.POOL_TIME = 10
        name, file_length = message.split()
        helper = BinaryUploadHelper(int(file_length), self.end_recv_svg, name, flag, args[0])
        self.set_binary_helper(helper)
        self.send_text('{"status": "continue"}')

    def end_recv_svg(self, buf, name, *args):
        self.POOL_TIME = self.POOL_TIME_
        if args[0] == 'upload':
            logger.debug("upload name:%s" % (name))
            try:
                self.m_laser_svg.svgs[name] = self.m_laser_svg.preprocess(buf, name)
                self.send_ok()
            except:
                print(sys.exc_info(), file=sys.stderr)
                sys.exc_info()[2].print_exception(file=sys.stderr)
                self.send_error('fail to parse svg')
        elif args[0] == 'compute':
            logger.debug("compute name:%s w[%.3f] h[%.3f] p1[%.3f, %.3f] p2[%.3f, %.3f] r[%f]" % (name, args[1][0], args[1][1], args[1][2], args[1][3], args[1][4], args[1][5], args[1][6]))
            params = args[1][:]  # copy
            params.pop(7)
            # [svg_buf, w, h, x1_real, y1_real, x2_real, y2_real, rotation, bitmap_w, bitmap_h, bitmap_buf]
            self.m_laser_svg.compute(name, [buf[:args[1][-3]]] + params + [buf[args[1][-3]:]])
            self.send_ok()

    def get(self, name):
        self.send_text('{"status": "continue", "length" : %d, "width": %f, "height": %f}' % (len(self.m_laser_svg.svgs[name][0]), self.m_laser_svg.svgs[name][1], self.m_laser_svg.svgs[name][2]))
        self.send_binary(self.m_laser_svg.svgs[name][0])

    def compute(self, params):
        options = params.split()
        name = options[0]
        w, h = float(options[1]), float(options[2])
        x1, y1, x2, y2 = (float(o) for o in options[3:7])
        rotation = float(options[7])
        svg_length = int(options[8])
        bitmap_w = int(options[9])
        bitmap_h = int(options[10])

        self.begin_recv_svg('%s %d' % (name, svg_length + bitmap_w * bitmap_h), 'compute', [w, h, x1, y1, x2, y2, rotation, svg_length, bitmap_w, bitmap_h])

    def go(self, params):
        names = params.split()
        gen_flag = '-f'
        if names[-1] == '-g' or names[-1] == '-f':
            gen_flag = names[-1]  # generate fcode or gcode
            names = names[:-1]
        logger.debug("upload names:%s" % (" ".join(names)))
        self.send_progress('initializing', 0.01)
        if gen_flag == '-f':
            output_binary = self.m_laser_svg.fcode_generate(names, self)

            ########## fake code  ########################
            with open('output.fc', 'wb') as f:
                f.write(output_binary)
            ##############################################

        elif gen_flag == '-g':
            output_binary = self.m_laser_svg.gcode_generate(names, self).encode()

            ########## fake code  ########################
            with open('output.gcode', 'wb') as f:
                f.write(output_binary)
            ##############################################

        self.send_progress('finishing', 1.0)

        self.send_text('{"status": "complete","length": %d}' % len(output_binary))
        self.send_binary(output_binary)
        logger.debug('laser svg finish')

    def set_params(self, params):
        key, value = params.split()
        self.m_laser_svg.set_params(key, value)
        self.send_ok()

    def meta_option(self, params):
        key, value = params.split()
        self.m_laser_bitmap.ext_metadata[key] = value
        self.send_ok()
