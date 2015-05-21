
from io import BytesIO
import logging

from fluxghost.utils.laser_pattern import laser_pattern
from .base import WebSocketBase, ST_NORMAL


logger = logging.getLogger("WS.LP")


"""
This websocket is use to convert bitmap to G-code

Javascript Example:

ws = new WebSocket("ws://localhost:8000/ws/laser-parser");
ws.onmessage = function(v) { console.log(v.data);}
ws.onclose = function(v) { console.log("CONNECTION CLOSED"); }

ws.send("100,100,1,WOOD")
buf = new ArrayBuffer(10000)
ws.send(buf)
"""


class WebsocketLaserParser(WebSocketBase):
    POOL_TIME = 30.0

    image_width = None
    image_height = None
    input_length = None
    ratio = None

    buf = None
    data_buffered = 0

    @classmethod
    def match_route(klass, path):
        return path == "laser-parser"

    def on_text_message(self, message):
        if self.input_length:
            logger.error("Recive undefined text: %s" % message)
        else:
            if self.set_params(message):
                self.send_text('{"status": "waitting_data"}')

    def on_binary_message(self, buf):
        if self.data_buffered < self.input_length:
            self.append_image_data(buf)

            if self.data_buffered == self.input_length:
                self.send('{"status": "received"}')
                self.process_image()
            elif self.data_buffered > self.input_length:
                raise RuntimeError("FILE_TOO_LARGE")
        else:
            logger.error("Recive undefined binary")

    def set_params(self, params):
        options = params.split(",")

        try:
            self.image_width = w = int(options[0], 10)
            self.image_height = h = int(options[1], 10)
            self.ratio = float(options[2])

            self.input_length = w * h
            if self.input_length > 1024 * 1024 * 8:
                raise RuntimeError("IMAGE_TOO_LARGE")

            self.buf = BytesIO()
            return True

        except ValueError:
            logger.exception("Laser argument error")
            self.send_fatal("BAD_PARAM_TYPE")

        except RuntimeError as e:
            self.send_fatal(e.args[0])

    def append_image_data(self, buf):
        l = self.buf.write(buf)
        self.data_buffered += l

        return self.data_buffered >= self.input_length
        if not self.data_buffered < self.input_length:
            self.send('{"status": "received"}')

        self.process_image()

    def process_image(self):
        buf = self.buf.getvalue()
        output_binary = laser_pattern(buf, self.image_width, self.image_height,
                                      self.ratio).encode()

        self.send_text('{"status": "processing", "prograss": 1.0}')
        self.send_text('{"status": "complete", "length": %s}' %
                       len(output_binary))

        bytes_sent = 0
        while len(output_binary) - bytes_sent > 1024:
            self.send_binary(output_binary[bytes_sent:bytes_sent + 1024])
            bytes_sent += 1024
        self.send_binary(output_binary[bytes_sent:])
        self.close(ST_NORMAL, "bye")
