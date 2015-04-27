
from datetime import datetime
from io import BytesIO
import logging

from .base import WebSocketBase, STATUS
from .laser_pattern import laser_pattern


logger = logging.getLogger("WS.LP")


"""
This websocket is use to convert bitmap to G-code

Javascript Example:

ws = new WebSocket("ws://localhost:8080/ws/laser-parser");
ws.onmessage = function(v) { console.log(v.data);}
ws.onclose = function(v) { console.log("CONNECTION CLOSED"); }

ws.send("100,100,1,WOOD")
buf = new ArrayBuffer(10000)
ws.send(buf)
"""


class WebsocketLaserParser(WebSocketBase):
    POOL_TIME = 30.0
    enable_timer = False

    image_width = None
    image_height = None
    input_length = None
    ratio = None

    buf = None
    data_buffered = 0

    @classmethod
    def match_route(klass, path):
        return path == "laser-parser"

    def onMessage(self, message, is_binary):
        if not self.input_length and not is_binary:
            self.set_params(message)
        elif self.data_buffered < self.input_length and is_binary:
            self.append_image_data(message)
        else:
            logger.error("Recive unknow data")

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
            self.send("continue")
        except ValueError:
            self.send("error BAD_PARAM_TYPE")
            self.close(STATUS.INVALID_PAYLOAD, "BAD_PARAM_TYPE")

        except RuntimeError as e:
            self.send("error %s" % e.args[0])
            self.close(STATUS.INVALID_PAYLOAD, e.args[0])

    def append_image_data(self, buf):
        l = self.buf.write(buf)
        self.data_buffered += l

        if not self.data_buffered < self.input_length:
            self.send("ok")

        self.process_image()

    def process_image(self):
        buf = self.buf.getvalue()
        output_binary = laser_pattern(buf, self.image_width, self.image_height, self.ratio).encode()

        # from hashlib import md5
        # output_binary = md5(buf).hexdigest().encode() + b'\n'
        self.send_text('1')

        self.send_text('length %i' % (len(output_binary)))
        bytes_sent = 0
        while len(output_binary) - bytes_sent > 1024:
            self.send_binary(output_binary[bytes_sent:bytes_sent+1024])
            bytes_sent += 1024
        self.send_binary(output_binary[bytes_sent:])
        self.close(STATUS.NORMAL, "bye")

    def on_loop(self):
        if self.enable_timer:
            self.send("Current Time: %s" % datetime.now())
