# !/usr/bin/env python3

import logging
import sys
import json
import io


from .base import WebSocketBase, WebsocketBinaryHelperMixin, \
    BinaryUploadHelper, ST_NORMAL, OnTextMessageMixin
from fluxclient.utils.fcode_parser import FcodeParser
from fluxclient.fcode.g_to_f import GcodeToFcode

logger = logging.getLogger("WS.fcode reader")


class WebsocketFcodeReader(OnTextMessageMixin, WebsocketBinaryHelperMixin, WebSocketBase):

    def __init__(self, *args):
        super(WebsocketFcodeReader, self).__init__(*args)
        self.cmd_mapping = {
            'upload': [self.begin_recv_buf],
            'get_img': [self.get_img],
            'get_meta': [self.get_meta],
            'get_path': [self.get_path],
            'get_fcode': [self.get_fcode]
        }
        self.fcode = None
        self.buf_type = '-f'

    def begin_recv_buf(self, length):
        logger.debug("begin upload g/f code")
        buf_type = '-f'

        length = length.split()
        print((length, len(length)))
        if len(length) == 2:
            length, buf_type = length
        else:
            length = length[0]
        file_size = int(length)
        if buf_type != '-g' and buf_type != '-f':
            self.send_fatal('TYPE_ERROR {}'.format(buf_type))
        else:
            self.buf_type = buf_type
            if buf_type == '-f':
                self.data_parser = FcodeParser()
            else:
                self.data_parser = GcodeToFcode()

            helper = BinaryUploadHelper(file_size, self.end_recv_buf)
            self.set_binary_helper(helper)
            self.send_continue()

    def end_recv_buf(self, buf):
        if self.buf_type == '-f':
            if self.data_parser.upload_content(buf):
                tmp = io.StringIO()
                self.data_parser.f_to_g(tmp)
                self.fcode = buf
                logger.debug("fcode parsing done")
                self.send_ok()
            else:
                self.send_error('File broken')
        else:
            f = io.StringIO()
            f.write(buf.decode('ascii', 'ignore'))
            f.seek(0)

            fcode_output = io.BytesIO()

            self.data_parser.process(f, fcode_output)
            self.fcode = fcode_output.getvalue()
            logger.debug("gcode parsing done")
            self.send_ok()

    def get_img(self, *args):
        buf = self.data_parser.get_img()
        if buf:
            self.send_text('{"status": "complete", "length": %d}' % len(buf))
            logger.debug('image length %d' % len(buf))

            self.send_binary(buf)
        else:
            logger.debug('get image: nothing to send')
            self.send_error('Nothing to send')

    def get_meta(self, *args):
        meta = self.data_parser.get_metadata()
        if meta:
            self.send_text('{"status": "complete", "metadata": %s}' % json.dumps(meta))
            logger.debug('sending metadata %d' % (len(meta)))
        else:
            logger.debug('get meta: nothing to send')
            self.send_error('Nothing to send')

    def get_path(self, *args):
        path = self.data_parser.get_path()
        if path:
            js_path = self.data_parser.path_to_js(path)
            logger.debug('sending path %d' % (len(path)))
            self.send_text(js_path)
        else:
            logger.debug('get path: nothing to send')
            self.send_error('No path data to send')

    def get_fcode(self, *args):
        if self.fcode:
            logger.debug('sending fcode %d' % (len(self.fcode)))
            self.send_text('{"status": "complete", "length": %d}' % len(self.fcode))
            self.send_binary(self.fcode)
        else:
            logger.debug('get fcode: nothing to send')
            self.send_error('No fcode to send')
