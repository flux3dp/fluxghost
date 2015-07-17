
from io import BytesIO
import logging

from .base import WebSocketBase, WebsocketBinaryHelperMixin, \
    BinaryUploadHelper, ST_NORMAL

from fluxclient.laser.laser_svg import LaserSvg

logger = logging.getLogger("WS.LP")

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
                    self.begin_recv_svg(params, 'upload')
                elif cmd == "get":
                    self.get(params)
                elif cmd == "compute":
                    self.compute(params)
                elif cmd == "go":
                    self.generate_gcode()
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

    def begin_recv_svg(self, message, flag):
        name, file_length = message.split(" ")
        helper = BinaryUploadHelper(int(file_length), self.end_recv_svg, name, flag)
        self.set_binary_helper(helper)
        self.send_text('{"status": "continue"}')

    def end_recv_svg(self, buf, name, *args):
        if args[0] == 'upload':
            self.m_laser_svg.preprocess(buf, name)
        elif args[0] == 'compute':
            self.m_laser_svg.compute(buf, name, args[1])

        self.send_text('{"status": "ok"}')

    def get(self, name):
        self.send_text('{"status": "continue", "length" : %d}' % len(self.m_laser_svg.svgs[name]))
        self.send_binary(self.m_laser_svg.svgs[name])

    def compute(self, params):
        options = params.split(' ')
        name = options[0]
        w, h = int(options[1]), int(options[2])
        x1, y1, x2, y2 = (float(o) for o in options[3:7])
        rotation = float(options[7])
        svg_length = int(options[8])
        self.begin_recv_svg('%s %d' % (name, svg_length), 'compute', [w, h, x1, y1, x2, y2, rotation])

    def generate_gcode(self):
        output_binary = self.m_laser_svg.gcode_generate().encode()
        self.send_text('{"status": "complete","length": %d}' % len(output_binary))
        self.send_binary(output_binary)
