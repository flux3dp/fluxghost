
from io import BytesIO
import logging

from .base import WebSocketBase, WebsocketBinaryHelperMixin, \
    BinaryUploadHelper, ST_NORMAL

from fluxclient.laser.laser_svg import LaserSvg

logger = logging.getLogger("WS.LP")

MODE_PRESET = "preset"
MODE_MANUALLY = "manually"


class WebsocketLaserSvgParser(WebsocketBinaryHelperMixin, WebSocketBase):
    POOL_TIME = 30.0
    operation = None

    # images, it will like
    # [
    #    [(x1, y1, x2, z2), (w, h), bytes],
    #    ....
    # ]
    m_laser_svg = LaserSvg()

    def on_text_message(self, message):
        try:
            if not self.operation:
                self.set_params(message)
                self.send_text('{"status": "ok"}')
            elif self.operation and not self.has_binary_helper():
                cmd, params = message.rstrip().split(" ", 1)

                if cmd == "go":
                    self.generate_gcode()
                elif cmd == "upload":
                    self.begin_recv_svg(params)
                    self.send_text('{"status": "ok"}')

                elif cmd == "get":
                    self.get(params)
                elif cmd == "compute":
                    self.compute(params)

                else:
                    self.begin_recv_image(message)
                    # self.recv_image(message)
                    self.send_text('{"status": "continue"}')
            else:
                raise RuntimeError("RESOURCE_BUSY")

        except ValueError:
            logger.exception("Laser argument error")
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

    def begin_recv_svg(self, message):
        name, file_length = message.split(" ")
        helper = BinaryUploadHelper(int(file_length), self.end_recv_svg, name)
        self.set_binary_helper(helper)
        self.send_text('{"status": "continue"}')

    def end_recv_svg(self, buf, name):
        m_laser_svg.pretreat(buf)
        self.m_laser_svg.svgs[name] = [buf]
        self.send_text('{"status": "accepted"}')

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
        self.begin_recv_svg('%s %d' % (name, svg_length, holder))

        self.m_laser_svg.svgs[name] += [w, h, x1, y1, x2, y2, rotation]
        self.send_text('{"status": "ok"}')

    def generate_gcode(self):
        output_binary = self.m_laser_svg.gcode_generate().encode()
        self.send_text('{"status": "complete","length": %d}' % len(output_binary))
        self.send_binary(output_binary)
