# !/usr/bin/env python3

import logging
import sys


from .base import WebSocketBase, WebsocketBinaryHelperMixin, \
    BinaryUploadHelper, ST_NORMAL
from fluxclient.laser.laser_bitmap import LaserBitmap

logger = logging.getLogger("WS.Laser Bitmap")

MODE_PRESET = "preset"
MODE_MANUALLY = "manually"


class WebsocketLaserBitmapParser(WebsocketBinaryHelperMixin, WebSocketBase):
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
                message = message.rstrip().split(" ", 1)
                if len(message) == 1:
                    cmd = message[0]
                    params = ''
                else:
                    cmd = message[0]
                    params = message[1]

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
        self.send_ok()

    def process_image(self):
        logger.debug('  start process images')
        self.send_progress('initializing', 0.03)

        layer_index = 0
        for position, size, rotation, thres, buf in self.images:
            layer_index += 1
            self.send_progress('processing image %d' % (layer_index), (layer_index / len(self.images) * 0.6 + 0.03))
            self.m_laser_bitmap.add_image(buf, size[0], size[1], position[0], position[1], position[2], position[3], rotation, thres)
            logger.debug("add image at %s pixel: %s" % (position, size))

        logger.debug("add image finished, generating gcode")
        self.send_progress('generating gcode', 0.97)
        output_binary = self.m_laser_bitmap.gcode_generate().encode()

        ########## fake code  ########################
        with open('output.gcode', 'wb') as f:
            f.write(output_binary)
        ##############################################

        self.send_progress('finishing', 1.0)
        self.send_text('{"status": "complete", "length": %s}' % len(output_binary))
        self.send_binary(output_binary)
        logger.debug("laser bitmap finished")

        self.close(ST_NORMAL, "bye")
