
"""
This websocket is use to slicing stl model

"""

from io import BytesIO
import logging


from .base import WebSocketBase, WebsocketBinaryHelperMixin, \
    BinaryUploadHelper, ST_NORMAL, SIMULATE

from fluxclient.printer.stl_slicer import StlSlicer, StlSlicerNoPCL

logger = logging.getLogger("WS.slicing")


class Websocket3DSlicing(WebsocketBinaryHelperMixin, WebSocketBase):
    POOL_TIME = 30.0

    def __init__(self, *args):
        WebSocketBase.__init__(self, *args)
        if not SIMULATE:
            logger.info("Using StlSlicer()")
            self.m_stl_slicer = StlSlicer()

        elif SIMULATE:
            logger.info("Using StlSlicerNoPcl()")
            self.m_stl_slicer = StlSlicerNoPCL()

    def on_text_message(self, message):
        try:
            if not self.has_binary_helper():
                cmd, params = message.rstrip().split(" ", 1)
                if cmd == 'upload':
                    logger.debug("upload %s" % (params))
                    self.begin_recv_stl(params, 'upload')
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
        name, file_length = params.split(' ')
        helper = BinaryUploadHelper(int(file_length), self.end_recv_stl, name, flag)
        self.set_binary_helper(helper)
        self.send_text('{"status": "continue"}')

    def end_recv_stl(self, buf, name, *args):
        if args[0] == 'upload':
            self.m_stl_slicer.upload(name, buf)

        self.send_text('{"status": "ok"}')

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

        self.send_text('{"status": "ok"}')

    def set_params(self, params):
        key, value = params.split(' ')
        if self.m_stl_slicer.set_params(key, value):  # will check if key is valid
            self.send_text('{"status": "ok"}')
        else:
            self.send_error('wrong parameter: %s' % key)

    def generate_gcode(self, params):
        names = params.split(' ')
        gcode, metadata = self.m_stl_slicer.generate_gcode(names)
        self.send_text('{"status": "complete", "length": %d, "time": %.3f, "filament_length": %.2f}' % (len(gcode), metadata[0], metadata[1]))
        self.send_binary(gcode.encode())

    def delete(self, params):
        name = params.rstrip()
        self.m_stl_slicer.delete(name)
        self.send_text('{"status": "ok"}')
