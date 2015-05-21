
from io import BytesIO
import logging

from .base import WebSocketBase, ST_NORMAL


logger = logging.getLogger("WS.LP")


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

MODE_PRESET = "preset"
MODE_MANUALLY = "manually"


class WebsocketBitmapLaserParser(WebSocketBase):
    POOL_TIME = 30.0

    operation = None

    image_params = None
    image_size = None
    image_buffered = None
    image_buffer = None

    # images, it will like
    # [
    #    [(x1, y1, x2, z2), (w, h), bytes],
    #    ....
    # ]
    images = []

    @classmethod
    def match_route(klass, path):
        return path == "bitmap-laser-parser"

    def on_text_message(self, message):
        try:
            if not self.operation:
                self.set_params(message)
                self.send_text('{"status": "ok"}')
            elif self.operation and self.image_buffer is None:
                if message == "go":
                    self.process_image()
                else:
                    self.recv_image(message)
                    self.send_text('{"status": "continue"}')
            else:
                raise RuntimeError("RESOURCE_BUSY")

        except ValueError:
            logger.exception("Laser argument error")
            self.send_fatal("BAD_PARAM_TYPE")

        except RuntimeError as e:
            self.send_fatal(e.args[0])

    def on_binary_message(self, buf):
        if self.image_buffer:
            self.append_image_data(buf)
        else:
            logger.error("Recive undefined binary")
            self.send_fatal("BAD_PARAM_TYPE")

    def set_params(self, params):
        options = params.split(",")

        if options[0] == "0":
            self.operation = MODE_PRESET

            operation = options[1]
            material = options[2]
            raise RuntimeError("TODO: parse operation and material")
            self.laser_speed = 100.0
            self.duty_cycle = 100.0

        elif options[0] == "1":
            self.operation = MODE_MANUALLY

            self.laser_speed = float(options[1])
            self.duty_cycle = float(options[2])
        else:
            raise RuntimeError("BAD_PARAM_TYPE")

    def recv_image(self, message):
        options = message.split(",")

        w, h = int(options[0]), int(options[1])
        x1, y1, x2, y2 = (float(o) for o in options[2:6])
        image_size = w * h

        logger.debug("Start image at [%.4f, %.4f][%.4f,%.4f] x [%i, %i]" %
                     (x1, y1, x2, y2, w, h))
        if image_size > 1024 * 1024 * 8:
            raise RuntimeError("IMAGE_TOO_LARGE")

        buf = BytesIO()
        self.image_params = [(x1, y1, x2, y2), (w, h), buf]
        self.image_size = image_size
        self.image_buffered = 0
        self.image_buffer = buf

    def append_image_data(self, buf):
        l = self.image_buffer.write(buf)
        self.image_buffered += l

        if self.image_buffered == self.image_size:
            self.images.append(self.image_params)
            self.image_params = None
            self.image_size = None
            self.image_buffered = None
            self.image_buffer = None

            self.send('{"status": "received"}')
        elif self.image_buffered > self.image_size:
            logger.error("File sent %i bytes, but should be %i bytes" %
                         (self.image_buffered, self.image_size))
            raise RuntimeError("FILE_TOO_LARGE")

    def process_image(self):
        output_binary = b"WOW1234"

        # <<<<<<<< Sample code for read all images
        layer_index = 0
        total = float(len(self.images))

        for position, size, buf in self.images:
            logger.debug("Process image at %s pixel: %s" % (position, size))
            progress = layer_index / total
            self.send_text(
                '{"status": "processing", "prograss": %.3f}' % progress)
            layer_index += 1

        self.send_text('{"status": "processing", "prograss": 1.0}')
        self.send_text('{"status": "complete", "length": %s}' %
                       len(output_binary))

        output_binary = b"Fake output result"
        # >>>>>>>> Sample code for read all images

        bytes_sent = 0
        while len(output_binary) - bytes_sent > 1024:
            self.send_binary(output_binary[bytes_sent:bytes_sent + 1024])
            bytes_sent += 1024
        self.send_binary(output_binary[bytes_sent:])
        self.close(ST_NORMAL, "bye")
