
"""
This websocket is use to convert bitmap to G-code

Javascript Example:

ws = new WebSocket("ws://localhost:8000/ws/bitmap-laser-parser");
ws.onmessage = function(v) { console.log(v.data);}
ws.onclose = function(v) { console.log("CONNECTION CLOSED"); }

ws.send("0,1,WOOD")
ws.send("100,100,-3,-3,3,3")
buf = new ArrayBuffer(10000)
ws.send(buf)
ws.send('go')
"""

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
    images = None

    def on_text_message(self, message):
        try:
            if not self.operation:
                self.set_params(message)
                self.send_text('{"status": "ok"}')
            elif self.operation and not self.has_binary_helper():
                if message == "go":
                    self.process_image()
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
        options = params.split(",")
        self.images = []

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

    def begin_recv_image(self, message):
        options = message.split(",")

        w, h = int(options[0]), int(options[1])
        x1, y1, x2, y2 = (float(o) for o in options[2:6])
        rotation = float(options[6])
        svg_len = int(options[7])

        logger.debug("Start image at [%.4f, %.4f][%.4f,%.4f] x [%i, %i], rotation = %.4f svg_len = %d" %
                     (x1, y1, x2, y2, w, h, rotation, svg_len))
        if image_size > 1024 * 1024 * 8:
            raise RuntimeError("IMAGE_TOO_LARGE")

        helper = BinaryUploadHelper(svg_len, self.end_recv_image,
                                    (x1, y1, x2, y2), (w, h), rotation, svg_len)
        self.set_binary_helper(helper)

    def end_recv_image(self, buf, position, size, rotation, svg_len):
        self.images.append((position, size, rotation, svg_len, buf))
        self.send_text('{"status": "accept"}')

    def process_image(self):
        m_laser_svg = LaserSvg()

        layer_index = 0
        total = float(len(self.images))

        for position, size, rotation, svg_len, buf in self.images:
            m_laser_svg.add_image(buf, size[0], size[1], position[0], position[1], position[2], position[3], rotation)

            logger.debug("Process image at %s pixel: %s" % (position, size))
            progress = layer_index / total
            self.send_text(
                '{"status": "processing", "prograss": %.3f}' % progress)
            layer_index += 1
        output_binary = m_laser_svg.gcode_generate().encode()

        self.send_text('{"status": "processing", "prograss": 1.0}')
        self.send_text('{"status": "complete", "length": %s}' %
                       len(output_binary))

        self.send_binary(output_binary)

        self.close(ST_NORMAL, "bye")