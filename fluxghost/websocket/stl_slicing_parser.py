
"""
This websocket is use to slicing stl model

"""

from io import BytesIO
import logging


from .base import WebSocketBase, WebsocketBinaryHelperMixin, \
    BinaryUploadHelper, ST_NORMAL


logger = logging.getLogger("WS.LP")


class Websocket3DSlicing(WebsocketBinaryHelperMixin, WebSocketBase):
    POOL_TIME = 30.0

    m_stl_slicer = StlSlicer()

    def on_text_message(self, message):
        try:
            elif self.operation and not self.has_binary_helper():
                cmd, params = message.rstrip().split(" ", 1)
                if cmd == 'upload':
                    self.begin_recv_stl(params, 'upload')
                elif cmd == 'set':
                    self.set(params)
                elif cmd == 'go':
                    self.generate_gcode(params)
                else:
                    raise ValueError('Undefine command %s' % (cmd))

            else:
                raise RuntimeError("RESOURCE_BUSY")

        except ValueError:
            logger.exception("slicing argument error")
            self.send_fatal("BAD_PARAM_TYPE")

        except RuntimeError as e:
            self.send_fatal(e.args[0])

    def begin_recv_stl(self, params, flag):
        name, file_length = params.split(' ')
        helper = BinaryUploadHelper(int(file_length), self.end_recv_stl, name, flag)
        self.set_binary_helper(helper)
        self.send_text('{"status": "continue"}')

    def end_recv_stl(self, buf, name, *args):
        if args[0] == 'upload':
            self.m_stl_slicer.upload(buf, name)

        self.send_text('{"status": "ok"}')

    def set(self, params):
        params = params.split(' ')
        assert len(params) == 8, 'wrong number of parameters %d' % len(params)
        name = params[0]
        position_x = float(params[1])
        position_y = float(params[2])
        position_z = float(params[3])
        rotation_x = float(params[4])
        rotation_y = float(params[5])
        rotation_z = float(params[6])
        scale = float(params[7])
        self.m_stl_slicer.set(name, [position_x, position_y, position_z, rotation_x, rotation_y, rotation_z, scale])

        self.send_text('{"status": "ok"}')

    def generate_gcode(self, params):
        names = params.split(' ')
        gcode_buf, metadata = self.m_stl_slicer.generate_gcode(names)
        self.send_text('{status: "complete",length: %d, time: %d}' % (len(gcode_buf), int(metadata[0])))
        self.send_binary(gcode_buf)
