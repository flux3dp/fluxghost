
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
buf = new ArrayBuffer(450)
ws.send(buf)
"""

from io import BytesIO
import logging
import struct
import os
import re

from .base import WebSocketBase, WebsocketBinaryHelperMixin, \
    BinaryUploadHelper, ST_NORMAL

logger = logging.getLogger("WS.3DSCAN-MODELING")


class Websocket3DScannModeling(WebsocketBinaryHelperMixin, WebSocketBase):
    def __init__(self, *args):
        WebSocketBase.__init__(self, *args)

        self._data_sets = {}
        self._base_data_set = None

        self._uploading = None

    def on_text_message(self, message):
        try:
            if self.has_binary_helper():
                raise RuntimeError("PROTOCOL_ERROR", "under uploading mode")

            cmd, params = message.split(" ", 1)

            if cmd == "upload":
                self._begin_upload(params)
                self.send_text('{"status": "continue"}')

            elif cmd == "base":
                self.set_base(params)

            elif cmd == "cut":
                pass
            elif cmd == "delete_noise":
                pass
            elif cmd == "dump":
                pass
            elif cmd == "export":
                pass
        except RuntimeError as e:
            self.send_fatal(e.args[0])
            logger.error(e)
        except Exception as e:
            self.send_fatal("UNKNOW_ERROR")
            raise

    def _begin_upload(self, params): #name, left_len, right_len="0"
        splited_params = params.split(" ")
        try:
            name = splited_params[0]
            s_left_len = splited_params[1]
            s_right_len = splited_params[2] if len(splited_params) > 2 else "0"

            llen = int(s_left_len)
            rlen = int(s_right_len)
            totel_length = (llen + rlen) * 15
        except ValueError:
            raise RuntimeError("BAD_PARAM_TYPE", "upload param error")


        helepr = BinaryUploadHelper(totel_length, self._end_upload,
                                    name, llen, rlen)
        self.set_binary_helper(helepr)
        self.send_text('{"status": "continue"}')

    def _end_upload(self, buf, name, left_len, right_len):
        left_points = buf[:left_len*15]
        right_points = buf[left_len*15:]

        self._data_sets[name] = (left_points, right_points)
        self.send_text('{"status": "ok"}')

    def set_base(self, name):
        if name in self._data_sets:
            self._base_data_set = object()

    def cut(self, name, z0, z1, r):
        pass

    def delete_noise(self, name, r):
        pass

    def dump(self, name):
        pass

    def export(self):
        pass