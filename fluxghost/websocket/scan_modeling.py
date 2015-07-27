
"""
Scan Modelling tool sets

Javascript Example:

ws = new WebSocket(
    "ws://localhost:8000/ws/3d-scan-modeling");
ws.onmessage = function(v) { console.log(v.data);}
ws.onclose = function(v) { console.log("CONNECTION CLOSED, code=" + v.code +
    "; reason=" + v.reason); }

// After recive connected...
ws.send("upload MySet1 15 15")
buf = new ArrayBuffer(720) // (15 + 15) * 24
ws.send(buf)
"""

from io import BytesIO
import logging
import struct
import os
import re

from .base import WebSocketBase, WebsocketBinaryHelperMixin, \
    BinaryUploadHelper, SIMULATE

from fluxclient import SUPPORT_PCL
from fluxclient.scanner.pc_process import PcProcess, PcProcessNoPCL

logger = logging.getLogger("WS.3DSCAN-MODELING")


class Websocket3DScannModeling(WebsocketBinaryHelperMixin, WebSocketBase):
    def __init__(self, *args):
        WebSocketBase.__init__(self, *args)

        if not SIMULATE:
            self.m_pc_process = PcProcess()
        if SIMULATE:
            self.m_pc_process = PcProcessNoPCL()

        self._uploading = None

    def on_text_message(self, message):
        try:
            if self.has_binary_helper():
                raise RuntimeError("PROTOCOL_ERROR", "under uploading mode")

            cmd, params = message.split(" ", 1)

            if cmd == "upload":
                self._begin_upload(params)

            elif cmd == "base":
                self.set_base(params)

            elif cmd == "cut":
                self.cut(params)

            elif cmd == "delete_noise":
                self.delete_noise(params)
            elif cmd == "dump":
                self.dump(params)
            elif cmd == "export":
                self.export(params)

        except RuntimeError as e:
            self.send_fatal(e.args[0])
            logger.error(e)
        except Exception as e:
            self.send_fatal("UNKNOW_ERROR")
            raise

    def _begin_upload(self, params):  # name, left_len, right_len="0"
        splited_params = params.split(" ")
        try:
            name = splited_params[0]
            s_left_len = splited_params[1]
            s_right_len = splited_params[2] if len(splited_params) > 2 else "0"

            llen = int(s_left_len)
            rlen = int(s_right_len)
            totel_length = (llen + rlen) * 24
        except ValueError:
            raise RuntimeError("BAD_PARAM_TYPE", "upload param error")
        logger.debug('uploading ' + name)
        helepr = BinaryUploadHelper(totel_length, self._end_upload,
                                    name, llen, rlen)
        self.set_binary_helper(helepr)
        self.send_text('{"status": "continue"}')

    def _end_upload(self, buf, name, left_len, right_len):

        left_points = buf[:left_len * 24]
        right_points = buf[left_len * 24:]
        self.m_pc_process.upload(name, left_points, right_points, left_len, right_len)
        self.send_text('{"status": "ok"}')

    def cut(self, params):
        name_in, name_out, mode, direction, value = params.split(" ")
        value = float(value)
        direction = direction[0] == 'T'
        self.m_pc_process.cut(name_in, name_out, mode, direction, value)
        self.send_text('{"status": "ok"}')

    def delete_noise(self, params):
        if not SUPPORT_PCL:
            self.send_text('{"status": "ok"}')
            return

        name_in, name_out, r = params.split(" ")
        r = float(r)
        self.m_pc_process.delete_noise(name_in, name_out, r)
        self.send_text('{"status": "ok"}')

    def dump(self, params):
        name = params
        len_L, len_R, buffer_data = self.m_pc_process.dump(name)
        self.send_text('{"status": "continue", "left": %d, "right": %d}' % (len_L, len_R))
        print(len(buffer_data), '{"status": "continue", "left": %d, "right": %d}' % (len_L, len_R))
        self.send_binary(buffer_data)
        self.send_text('{"status": "ok"}')
        logger.debug('dump %s done' % (name))

    def export(self, params):
        name, file_foramt = params.split(" ")
        buf = self.m_pc_process.export(name, file_foramt)
        self.send_text('{"status": "continue", "length": %d}' % (len(buf)))
        self.send_binary(buf)
        self.send_text('{"status": "ok"}')
        logger.debug('export %s as .%s file done' % (name, file_foramt))
