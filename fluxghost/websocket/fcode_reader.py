# !/usr/bin/env python3

import logging
import sys
import json
from io import StringIO, BytesIO

from PIL import Image

from .base import WebSocketBase, WebsocketBinaryHelperMixin, \
    BinaryUploadHelper, ST_NORMAL, OnTextMessageMixin
from fluxclient.utils.fcode_parser import FcodeParser
from fluxclient.fcode.g_to_f import GcodeToFcode

logger = logging.getLogger(__name__)


class WebsocketFcodeReader(OnTextMessageMixin, WebsocketBinaryHelperMixin, WebSocketBase):

    def __init__(self, *args):
        super(WebsocketFcodeReader, self).__init__(*args)
        self.cmd_mapping = {
            'upload': [self.begin_recv_buf, 'upload'],
            'get_img': [self.get_img],
            'get_meta': [self.get_meta],
            'get_path': [self.get_path],
            'get_fcode': [self.get_fcode],
            'change_img': [self.begin_recv_buf, 'change_img']
        }
        self.fcode = None
        self.buf_type = '-f'

    def begin_recv_buf(self, length, flag):
        if flag == 'upload':
            logger.debug("begin upload g/f code")
            buf_type = '-f'

            length = length.split()
            if len(length) == 2:
                length, buf_type = length
            else:
                length = length[0]
            file_size = int(length)
            if buf_type != '-g' and buf_type != '-f':
                self.send_fatal('TYPE_ERROR {}'.format(buf_type))
                return
            self.buf_type = buf_type
            if buf_type == '-f':
                self.data_parser = FcodeParser()
            else:
                self.data_parser = GcodeToFcode()
        elif flag == 'change_img':
            file_size = int(length)
        else:
            logger.error('wrong argument')
            raise RuntimeError('api fail')

        helper = BinaryUploadHelper(file_size, self.end_recv_buf, flag)
        self.set_binary_helper(helper)
        self.send_continue()

    def end_recv_buf(self, buf, flag):
        if flag == 'upload':
            if self.buf_type == '-f':
                if self.data_parser.upload_content(buf):
                    tmp = StringIO()
                    self.data_parser.f_to_g(tmp)
                    self.fcode = buf
                    logger.debug("fcode parsing done")
                    self.send_ok()
                else:
                    self.send_error('File broken')
            else:
                f = StringIO()
                f.write(buf.decode('ascii', 'ignore'))
                f.seek(0)

                fcode_output = BytesIO()

                self.data_parser.process(f, fcode_output)
                self.fcode = fcode_output.getvalue()
                logger.debug("gcode parsing done")
                self.send_ok()
        elif flag == 'change_img':
            self.change_img(buf)

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

    def change_img(self, buf):
        b = BytesIO()
        b.write(buf)
        img = Image.open(b)
        img = img.resize((640, 640))  # resize preview image

        b = BytesIO()
        img.save(b, 'png')
        img_bytes = b.getvalue()

        if self.buf_type == '-f':
            self.data_parser.change_img(img_bytes)
            self.fcode = self.data_parser.data
        else:
            tmp_data_parser = FcodeParser()
            tmp_data_parser.upload_content(self.fcode)
            tmp_data_parser.change_img(img_bytes)

            self.data_parser.image = img_bytes
            self.fcode = tmp_data_parser.data

        self.send_ok()
