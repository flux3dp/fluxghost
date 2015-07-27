
from io import BytesIO
import logging

from .base import WebSocketBase, WebsocketBinaryHelperMixin, \
    BinaryUploadHelper, ST_NORMAL

from fluxclient.laser.laser_svg import LaserSvg

logger = logging.getLogger("WS.Laser Svg")

MODE_PRESET = "preset"
MODE_MANUALLY = "manually"


class WebsocketLaserSvgParser(WebsocketBinaryHelperMixin, WebSocketBase):
    operation = None

    m_laser_svg = LaserSvg()

    def on_text_message(self, message):
        try:
            if not self.operation:
                self.set_params(message)
                self.send_text('{"status": "ok"}')
            elif self.operation and not self.has_binary_helper():
                cmd, params = message.rstrip().split(" ", 1)

                if cmd == "upload":

                    self.begin_recv_svg(params, 'upload', None)
                elif cmd == "get":
                    self.get(params)
                elif cmd == "compute":
                    self.compute(params)
                elif cmd == "go":
                    self.go(params)
                else:
                    raise ValueError('Undefine command %s' % (cmd))
            else:
                raise RuntimeError("RESOURCE_BUSY")

        except ValueError:
            logger.exception("Laser svg argument error")
            self.send_fatal("BAD_PARAM_TYPE")

        except RuntimeError as e:
            self.send_fatal(e.args[0])

    def set_params(self, params):
        options = params.split(" ")

        if options[0] == "0":
            self.operation = MODE_PRESET

            self.operation = options[1]
            self.material = options[2]
            # raise RuntimeError("TODO: parse operation and material")
            self.laser_speed = 100.0
            self.duty_cycle = 100.0

        elif options[0] == "1":
            self.operation = MODE_MANUALLY

            self.laser_speed = float(options[1])
            self.duty_cycle = float(options[2])
        else:
            raise RuntimeError("BAD_PARAM_TYPE")

    def begin_recv_svg(self, message, flag, *args):
        name, file_length = message.split(" ")
        helper = BinaryUploadHelper(int(file_length), self.end_recv_svg, name, flag, args[0])
        self.set_binary_helper(helper)
        self.send_text('{"status": "continue"}')

    def end_recv_svg(self, buf, name, *args):
        if args[0] == 'upload':
            logger.debug("upload name:%s" % (name))
            self.m_laser_svg.preprocess(buf, name)
            self.send_text('{"status": "ok"}')
        elif args[0] == 'compute':
            logger.debug("compute name:%s w[%.3f] h[%.3f] p1[%.3f, %.3f] p2[%.3f, %.3f] r[%f]" % (name, args[1][0], args[1][1], args[1][2], args[1][3], args[1][4], args[1][5], args[1][6]))
            self.m_laser_svg.compute(buf[:args[1][-2]], name, args[1][:-2] + [buf[args[1][-2]:]])
            self.send_text('{"status": "ok"}')

    def get(self, name):
        self.send_text('{"status": "continue", "length" : %d, "width": %f, "height": %f}' % (len(self.m_laser_svg.svgs[name][0]), self.m_laser_svg.svgs[name][1], self.m_laser_svg.svgs[name][2]))
        self.send_binary(self.m_laser_svg.svgs[name][0])

    def compute(self, params):
        options = params.split(' ')
        name = options[0]
        w, h = float(options[1]), float(options[2])
        x1, y1, x2, y2 = (float(o) for o in options[3:7])
        rotation = float(options[7])
        svg_length = int(options[8])
        bitmap_length = int(options[9])
        self.begin_recv_svg('%s %d' % (name, svg_length + bitmap_length), 'compute', [w, h, x1, y1, x2, y2, rotation, svg_length, bitmap_length])

    def go(self, params):
        names = params.split(' ')
        logger.debug("upload names:%s" % (" ".join(names)))

        output_binary = self.m_laser_svg.gcode_generate(names).encode()
        self.send_text('{"status": "complete","length": %d}' % len(output_binary))
        self.send_binary(output_binary)
