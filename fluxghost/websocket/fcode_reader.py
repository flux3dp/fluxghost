# !/usr/bin/env python3

import logging
import sys
import json
import io


from .base import WebSocketBase, WebsocketBinaryHelperMixin, \
    BinaryUploadHelper, ST_NORMAL, OnTextMessageMixin
from fluxclient.utils.fcode_parser import FcodeParser

logger = logging.getLogger("WS.fcode reader")


class WebsocketFcodeReader(OnTextMessageMixin, WebsocketBinaryHelperMixin, WebSocketBase):
    images = []
    _m_laser_bitmap = None

    def __init__(self, *args):
        super(WebsocketFcodeReader, self).__init__(*args)
        self.cmd_mapping = {
            'upload': [self.begin_recv_image],
            'get_img': [self.get_img],
            'get_meta': [self.get_meta],
            'get_path': [self.get_path]
        }
        self.m_fcode_parser = FcodeParser()

    def begin_recv_image(self, message):
        logger.debug("begin upload")
        file_size = int(message)

        helper = BinaryUploadHelper(file_size, self.end_recv_image)
        self.set_binary_helper(helper)
        self.send_continue()

    def end_recv_image(self, buf):
        if self.m_fcode_parser.upload_content(buf):
            tmp = io.StringIO()
            self.m_fcode_parser.f_to_g(tmp)
            logger.debug("fcode parsing done")
            self.send_ok()
        else:
            self.send_err('File broken')

    def get_img(self, *args):
        buf = self.m_fcode_parser.get_img()
        if buf:
            self.send_text('{"status": "complete", "length": %d}' % len(buf))
            logger.debug('image length %d' % len(buf))

            self.send_binary(buf)
        else:
            logger.debug('get image: othing to send')
            self.send_error('Nothing to send')

    def get_meta(self, *args):
        meta = self.m_fcode_parser.get_metadata()
        if meta:
            self.send_text('{"status": "complete", "metadata": %s}' % json.dumps(meta))
            logger.debug('sending metadata %d' % (len(meta)))
        else:
            logger.debug('get meta: othing to send')
            self.send_error('Nothing to send')

    def get_path(self, *args):
        path = self.m_fcode_parser.get_path()
        if path:
            js_path = self.m_fcode_parser.path_to_js(path)
            logger.debug('sending path %d' % (len(path)))
            self.send_text(js_path)
        else:
            logger.debug('get path: othing to send')
            self.send_error('No path data to send')
