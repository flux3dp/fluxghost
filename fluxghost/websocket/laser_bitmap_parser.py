
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

from fluxclient.laser.laser_bitmap import LaserBitmap

logger = logging.getLogger("WS.Laser Bitmap")

MODE_PRESET = "preset"
MODE_MANUALLY = "manually"


class WebsocketLaserBitmapParser(WebsocketBinaryHelperMixin, WebSocketBase):
    operation = None

    # images, it will like
    # [
    #    [(x1, y1, x2, z2), (w, h), bytes],
    #    ....
    # ]
    images = []
    _m_laser_bitmap = None

    @property
    def m_laser_bitmap(self):
        if self._m_laser_bitmap is None:
            self._m_laser_bitmap = LaserBitmap()
        return self._m_laser_bitmap

    def on_text_message(self, message):
        try:
            if not self.has_binary_helper():
                cmd = message.rstrip().split(" ", 1)
                if len(cmd) == 1:
                    cmd = cmd[0]
                else:
                    params = cmd[1]
                    cmd = cmd[0]

                if cmd == "go":
                    self.process_image()
                elif cmd == 'set_params':
                    self.set_params(params)
                elif cmd == 'upload':
                    self.begin_recv_image(params)
                else:
                    raise ValueError('undefine command')
            else:
                raise RuntimeError("RESOURCE_BUSY")

        except ValueError:
            logger.exception("Laser bitmap argument error: %s" % message)
            self.send_fatal("BAD_PARAM_TYPE")

        except RuntimeError as e:
            self.send_fatal(e.args[0])

    # def preset(self, params):
    #     logger.debug("  Set params: %s" % params)
    #     options = params.split(" ")
    #     self.images = []

    #     if options[0] == "0":
    #         self.operation = MODE_PRESET

    #         self.operation = options[1]
    #         self.material = options[2]
    #         # raise RuntimeError("TODO: parse operation and material")
    #         self.laser_speed = 100.0
    #         self.duty_cycle = 100.0

    #     elif options[0] == "1":
    #         self.operation = MODE_MANUALLY

    #         self.laser_speed = float(options[1])
    #         self.duty_cycle = float(options[2])
    #     else:
    #         raise RuntimeError("BAD_PARAM_TYPE")

    def begin_recv_image(self, message):
        options = message.split(" ")
        w, h = int(options[0]), int(options[1])
        x1, y1, x2, y2 = (float(o) for o in options[2:6])
        rotation = float(options[6])
        thres = int(options[7])

        image_size = w * h

        logger.debug("  Start recv image at [%.4f, %.4f][%.4f,%.4f] x [%i, %i], rotation = %.4f thres = %d" %
                     (x1, y1, x2, y2, w, h, rotation, thres))
        if image_size > 1024 * 1024 * 8:
            raise RuntimeError("IMAGE_TOO_LARGE")

        helper = BinaryUploadHelper(image_size, self.end_recv_image,
                                    (x1, y1, x2, y2), (w, h), rotation, thres)
        self.set_binary_helper(helper)
        self.send_text('{"status": "continue"}')

    def end_recv_image(self, buf, position, size, rotation, thres):
        self.images.append((position, size, rotation, thres, buf))
        self.send_text('{"status": "accept"}')

    def set_params(self, params):
        key, value = params.split(' ')
        self.m_laser_bitmap.set_params(key, value)
        self.send_text('{"status": "ok"}')

    def process_image(self):
        logger.debug('  start process images')
        layer_index = 0
        total = float(len(self.images))

        for position, size, rotation, thres, buf in self.images:
            self.m_laser_bitmap.add_image(buf, size[0], size[1], position[0], position[1], position[2], position[3], rotation, thres)

            logger.debug("Process image at %s pixel: %s" % (position, size))
            progress = layer_index / total
            self.send_text(
                '{"status": "processing", "progress": %.3f}' % progress)
            layer_index += 1
        output_binary = self.m_laser_bitmap.gcode_generate().encode()

        ########## fake code  ########################
        with open('output.gcode', 'wb') as f:
            f.write(output_binary)
        ##############################################

        self.send_text('{"status": "processing", "progress": 1.0}')
        self.send_text('{"status": "complete", "length": %s}' %
                       len(output_binary))
        self.send_binary(output_binary)

        self.close(ST_NORMAL, "bye")
