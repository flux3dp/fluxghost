
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

from io import BytesIO
import logging

from fluxghost.utils.laser_pattern import laser_pattern
from .base import WebSocketBase, WebsocketBinaryHelperMixin, \
    BinaryUploadHelper, ST_NORMAL


logger = logging.getLogger("WS.LP")


class WebsocketLaserParser(WebsocketBinaryHelperMixin, WebSocketBase):
    POOL_TIME = 30.0

    image_width = None
    image_height = None
    input_length = None
    ratio = None

    buf = None
    data_buffered = 0

    def on_text_message(self, message):
        if self.input_length:
            logger.error("Recive undefined text: %s" % message)
        else:
            if self.set_params(message):
                self.send_text('{"status": "waitting_data"}')

    def set_params(self, params):
        options = params.split(",")

        try:
            self.image_width = w = int(options[0], 10)
            self.image_height = h = int(options[1], 10)
            self.ratio = float(options[2])

            self.input_length = w * h
            if self.input_length > 1024 * 1024 * 8:
                raise RuntimeError("IMAGE_TOO_LARGE")

            self._binary_helper = BinaryUploadHelper(self.input_length,
                                                     self.upload_finished)
            return True

        except ValueError:
            logger.exception("Laser argument error")
            self.send_fatal("BAD_PARAM_TYPE")

        except RuntimeError as e:
            self.send_fatal(e.args[0])

    def upload_finished(self, buf):
        self.process_image(buf)

    def process_image(self, buf):
        output_binary = laser_pattern(buf, self.image_width, self.image_height,
                                      self.ratio).encode()

        self.send_text('{"status": "processing", "prograss": 1.0}')
        self.send_text('{"status": "complete", "length": %s}' %
                       len(output_binary))

        self.send_binary(output_binary)
        self.close(ST_NORMAL, "bye")
