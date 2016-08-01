from io import StringIO, BytesIO
from os import environ
import logging
import json

from PIL import Image

from fluxclient.fcode.f_to_g import FcodeToGcode
from fluxclient.fcode.g_to_f import GcodeToFcode
from fluxclient.hw_profile import HW_PROFILE
from .misc import BinaryUploadHelper, BinaryHelperMixin, OnTextMessageMixin

logger = logging.getLogger("API.FCODE_READER")


def fcode_reader_api_mixin(cls):
    class FcodeReaderApi(BinaryHelperMixin, OnTextMessageMixin, cls):
        def __init__(self, *args):
            super().__init__(*args)
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
                    self.data_parser = FcodeToGcode()
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
                    res = self.data_parser.upload_content(buf)
                    if res == 'ok' or res == 'out_of_bound':
                        tmp = StringIO()
                        self.data_parser.f_to_g(tmp)
                        self.fcode = buf
                        logger.debug("fcode parsing done")
                        if res == 'ok':
                            self.send_ok()
                        elif res == 'out_of_bound':
                            self.send_error("6", info="gcode area too big")

                    elif res == 'broken':
                        self.send_error('15', info='File broken')
                else:  # -g gcode
                    f = StringIO()
                    f.write(buf.decode('ascii', 'ignore'))
                    f.seek(0)

                    fcode_output = BytesIO()
                    # try:
                    res = self.data_parser.process(f, fcode_output)
                    if res != 'broken':
                        self.fcode = fcode_output.getvalue()

                        if float(self.data_parser.md.get('MAX_X', 0)) > HW_PROFILE['model-1']['radius']:
                            self.send_error("6", info="gcode area too big")
                        elif float(self.data_parser.md.get('MAX_Y', 0)) > HW_PROFILE['model-1']['radius']:
                            self.send_error("6", info="gcode area too big")
                        elif float(self.data_parser.md.get('MAX_R', 0)) > HW_PROFILE['model-1']['radius']:
                            self.send_error("6", info="gcode area too big")
                        elif float(self.data_parser.md.get('MAX_Z', 0)) > HW_PROFILE['model-1']['height'] or float(self.data_parser.md.get('MAX_Z', 0)) < 0:
                            self.send_error("6", info="gcode area too big")
                        else:
                            self.send_ok()
                        logger.debug("gcode parsing done")
                    else:
                        self.send_error('15', info='Parsing file fail')

            elif flag == 'change_img':
                self.change_img(buf)

            ########################
            if environ.get("flux_debug") == '1':
                if self.fcode:
                    with open('output.fc', 'wb') as f:
                        f.write(self.fcode)
            ########################

        def get_img(self, *args):
            buf = self.data_parser.get_img()
            if buf:
                self.send_text('{"status": "complete", "length": %d}' % len(buf))
                logger.debug('image length %d' % len(buf))

                self.send_binary(buf)
            else:
                logger.debug('get image: nothing to send')
                self.send_error('8', info='No image to send')

        def get_meta(self, *args):
            meta = self.data_parser.get_metadata()
            if meta:
                self.send_text('{"status": "complete", "metadata": %s}' % json.dumps(meta))
                logger.debug('sending metadata %d' % (len(meta)))
            else:
                logger.debug('get meta: nothing to send')
                self.send_error('8', info='No metadata to send')

        def get_path(self, *args):
            if self.data_parser.path:
                js_path = self.data_parser.get_path(path_type='js')
                logger.debug('sending path %d' % (len(js_path)))
                self.send_text(js_path)
            else:
                logger.debug('get path: nothing to send')
                self.send_error('9', info='No path data to send')

        def get_fcode(self, *args):
            if self.fcode:
                logger.debug('sending fcode %d' % (len(self.fcode)))
                self.send_text('{"status": "complete", "length": %d}' % len(self.fcode))
                self.send_binary(self.fcode)
                ######################### fake code ###################################
                if environ.get("flux_debug") == '1':
                    with open('output.fc', 'wb') as f:
                        f.write(self.fcode)
                ############################################################
            else:
                logger.debug('get fcode: nothing to send')
                self.send_error('8', info='No fcode to send')

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
                tmp_data_parser = FcodeToGcode()
                tmp_data_parser.upload_content(self.fcode)
                tmp_data_parser.change_img(img_bytes)

                self.data_parser.image = img_bytes
                self.fcode = tmp_data_parser.data

            self.send_ok()
    return FcodeReaderApi
