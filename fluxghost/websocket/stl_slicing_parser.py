# !/usr/bin/env python3

from io import BytesIO
import logging
import sys


from .base import WebSocketBase, WebsocketBinaryHelperMixin, \
    BinaryUploadHelper, ST_NORMAL, SIMULATE
from fluxclient.printer.stl_slicer import StlSlicer

logger = logging.getLogger("WS.slicing")


class Websocket3DSlicing(WebsocketBinaryHelperMixin, WebSocketBase):
    """
    This websocket is use to slicing stl model
    """
    POOL_TIME = 30.0

    def __init__(self, *args):
        WebSocketBase.__init__(self, *args)
        logger.info("Using StlSlicer()")
        self.m_stl_slicer = StlSlicer()

    def on_text_message(self, message):
        try:
            if not self.has_binary_helper():
                message = message.rstrip().split(" ", 1)
                if len(message) == 1:
                    cmd, params = message[0], ''
                else:
                    cmd, params = message

                if cmd == 'upload':
                    logger.debug("upload %s" % (params))
                    self.begin_recv_stl(params, cmd)
                elif cmd == 'upload_image':
                    logger.debug("upload_image %s" % (params))
                    self.begin_recv_stl(params, cmd)

                elif cmd == 'set':
                    logger.debug("set %s" % (params))
                    self.set(params)
                elif cmd == 'go':
                    logger.debug("go %s" % (params))
                    self.generate_gcode(params)
                elif cmd == 'delete':
                    logger.debug("delete %s" % (params))
                    self.delete(params)
                elif cmd == 'set_params':
                    logger.debug("set_params %s" % (params))
                    self.set_params(params)
                elif cmd == 'advanced_setting':
                    logger.debug("advanced_setting %s" % (params))
                    self.advanced_setting(params)
                elif cmd == 'get_path':
                    # TODO
                    logger.debug("get_path")
                    self.get_path()
                else:
                    raise ValueError('Undefine command %s' % (cmd))

            else:
                raise RuntimeError("RESOURCE_BUSY")

        except ValueError:
            logger.exception("slicing argument error")
            self.send_fatal("BAD_PARAM_TYPE %s" % (message))

        except RuntimeError as e:
            self.send_fatal(e.args[0])

    def begin_recv_stl(self, params, flag):
        if flag == 'upload':
            name, file_length = params.split(' ')
        elif flag == 'upload_image':
            name = ''
            file_length = params
        helper = BinaryUploadHelper(int(file_length), self.end_recv_stl, name, flag)
        self.set_binary_helper(helper)
        self.send_text('{"status": "continue"}')

    def end_recv_stl(self, buf, *args):
        if args[1] == 'upload':
            self.m_stl_slicer.upload(args[0], buf)
        elif args[1] == 'upload_image':
            self.m_stl_slicer.upload_image(buf)
        self.send_ok()

    def set(self, params):
        params = params.split(' ')
        assert len(params) == 10, 'wrong number of parameters %d' % len(params)
        name = params[0]
        position_x = float(params[1])
        position_y = float(params[2])
        position_z = float(params[3])
        rotation_x = float(params[4])
        rotation_y = float(params[5])
        rotation_z = float(params[6])
        scale_x = float(params[7])
        scale_y = float(params[8])
        scale_z = float(params[9])
        self.m_stl_slicer.set(name, [position_x, position_y, position_z, rotation_x, rotation_y, rotation_z, scale_x, scale_y, scale_z])

        self.send_ok()

    def set_params(self, params):
        key, value = params.split(' ')
        if self.m_stl_slicer.set_params(key, value):  # will check if key is valid
            self.send_ok()
        else:
            self.send_error('wrong parameter: %s' % key)

    def advanced_setting(self, params):
        lines = params.split('\n')
        bad_line = self.m_stl_slicer.advanced_setting(lines)
        if bad_line == []:
            self.send_ok()
        else:
            for i in bad_line:
                self.send_error('line %d: %s error' % (i, lines[i]))

    def generate_gcode(self, params):
        names = params.split(' ')
        gcode, metadata = self.m_stl_slicer.generate_gcode(names, self)
        # self.send_progress('finishing', 1.0)
        if gcode:
            self.send_text('{"status": "complete", "length": %d, "time": %.3f, "filament_length": %.2f}' % (len(gcode), metadata[0], metadata[1]))
            self.send_binary(gcode.encode())
            logger.debug('slicing finish')
        else:
            self.send_error(metadata)
            logger.debug('slicing fail')

    def get_path(self):
        path = self.m_stl_slicer.get_path()
        if path:
            self.send_text(path)
        else:
            self.send_error('no path data to send')

    def delete(self, params):
        name = params.rstrip()
        flag, message = self.m_stl_slicer.delete(name)
        if flag:
            self.send_ok()
        else:
            self.send_error(message)
