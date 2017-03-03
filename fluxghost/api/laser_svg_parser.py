
import logging
import sys

from fluxclient.laser.laser_svg import LaserSvg
from fluxclient.toolpath import FCodeV1MemoryWriter, GCodeMemoryWriter
from .misc import BinaryUploadHelper, BinaryHelperMixin, OnTextMessageMixin

logger = logging.getLogger("API.LASER.SVG")

MODE_PRESET = "preset"
MODE_MANUALLY = "manually"


def laser_svg_parser_api_mixin(cls):
    class LaserSvgParserApi(BinaryHelperMixin, OnTextMessageMixin, cls):
        _m_laser_svg = None

        def __init__(self, *args):
            super().__init__(*args)
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
            logger.info('upload')
            self.POOL_TIME_ = self.POOL_TIME  # record pool time
            self.POOL_TIME = 10
            name, file_length = message.split()
            helper = BinaryUploadHelper(int(file_length), self.end_recv_svg, name, flag, args[0])
            self.set_binary_helper(helper)
            self.send_continue()

        def end_recv_svg(self, buf, name, *args):
            self.POOL_TIME = self.POOL_TIME_
            if args[0] == 'upload':
                logger.debug("  uploaded name:%s" % (name))
                try:
                    warning, content = self.m_laser_svg.preprocess(buf)

                    if warning and warning[-1] == 'EMPTY':  # if it's a empty svg for me
                        for w in warning[:-1]:
                            self.send_warning(w)
                        self.send_error(warning[-1])
                        logger.info('empty file')
                    else:
                        for w in warning:  # might be some recognized parts
                            self.send_warning(w)
                        self.m_laser_svg.svgs[name] = content
                        self.send_ok()
                        logger.debug('  end recv svg')
                except:
                    import traceback
                    traceback.print_tb(sys.exc_info()[2], file=sys.stderr)
                    logger.debug(repr(sys.exc_info()))
                    self.send_error('SVG_BROKEN')
                    logger.info('svg broken')

            elif args[0] == 'compute':
                logger.debug("compute name:%s w[%.3f] h[%.3f] p1[%.3f, %.3f] p2[%.3f, %.3f] r[%f]" % (name, args[1][0], args[1][1], args[1][2], args[1][3], args[1][4], args[1][5], args[1][6]))
                params = args[1][:]  # copy
                params.pop(7)
                # [svg_buf, w, h, x1_real, y1_real, x2_real, y2_real, rotation, bitmap_w, bitmap_h, bitmap_buf]
                self.m_laser_svg.compute(name, [buf[:args[1][-3]]] + params + [buf[args[1][-3]:]])
                logger.debug('  end recv preview image')
                self.send_ok()

        def get(self, name):
            logger.info('get name:{}'.format(name))
            if name in self.m_laser_svg.svgs:
                self.send_text('{"status": "continue", "length" : %d, "width": %f, "height": %f}' % (len(self.m_laser_svg.svgs[name][0]), self.m_laser_svg.svgs[name][1], self.m_laser_svg.svgs[name][2]))
                self.send_binary(self.m_laser_svg.svgs[name][0])
            else:
                self.send_error('%s not uploaded yet' % (name))

        def compute(self, params):
            logger.info('compute')
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
            logger.info("go names:%s flag:%s" % (" ".join(names), gen_flag))
            self.send_progress('initializing', 0.01)
            if gen_flag == '-f':
                writer = FCodeV1MemoryWriter("LASER", {}, ())
                self.m_laser_svg.process(writer, names, self)
                preview = self.m_laser_svg.dump(mode="preview")
                writer.set_previews((preview, ))
                writer.terminated()
                output_binary = writer.get_buffer()
                time_need = float(writer.get_metadata().get("TIME_COST", 0))

            elif gen_flag == '-g':
                writer = GCodeMemoryWriter()
                self.m_laser_svg.process(writer, names, self)
                output_binary = writer.get_buffer()
                writer.terminated()
                time_need = 0

            self.send_progress('finishing', 1.0)
            self.send_text('{"status": "complete", "length": %d, "time": %.3f}' % (len(output_binary), time_need))

            self.send_binary(output_binary)
            logger.info('laser svg finish')

        def set_params(self, params):
            key, value = params.split()
            self.m_laser_svg.set_params(key, value)
            self.send_ok()
            logger.info('set_params key:{}'.format(key))

        def meta_option(self, params):
            key, value = params.split()
            self.m_laser_bitmap.ext_metadata[key] = value
            self.send_ok()
            logger.info('meta_option key:{}'.format(key))

    return LaserSvgParserApi
