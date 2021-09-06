import logging
import os
import shutil
import subprocess
import tempfile

from .misc import BinaryUploadHelper, BinaryHelperMixin, OnTextMessageMixin

logger = logging.getLogger('API.UTILS')


# General utility api
def utils_api_mixin(cls):
    class UtilsApi(OnTextMessageMixin, BinaryHelperMixin, cls):
        def __init__(self, *args, **kw):
            super(UtilsApi, self).__init__(*args, **kw)
            self.cmd_mapping = {
                'pdf2svg': [self.cmd_pdf2svg],
                'upload_to': [self.cmd_upload_to],
                'select_font': [self.cmd_select_font],
                'check_exist': [self.cmd_check_exist],
            }

        def cmd_pdf2svg(self, params):
            params = params.split(' ')
            file_size = int(params[0])

            def upload_callback(buf):
                temp_pdf = tempfile.NamedTemporaryFile()
                temp_svg = tempfile.NamedTemporaryFile()
                temp_pdf.write(buf)
                temp_pdf.seek(0)
                try:
                    proc = subprocess.Popen(
                        ['pdf2svg', temp_pdf.name, temp_svg.name])
                    ret = proc.wait()

                    temp_svg.seek(0)
                    svg_content = temp_svg.read()
                    temp_pdf.close()
                    temp_svg.close()
                    if ret == 0:
                        self.send_binary(svg_content)
                    else:
                        self.send_error('Unable to convert file to SVG')
                except Exception as e:
                    self.send_error(str(e))

            helper = BinaryUploadHelper(int(file_size), upload_callback)
            self.set_binary_helper(helper)
            self.send_json(status='continue')

        def cmd_check_exist(self, params):
            params = params.split(' ')
            file_path = params[0]
            res = os.path.exists(file_path)
            self.send_ok(res=res)

        def cmd_select_font(self, params):
            params = params.split(' ')
            font_path = params[0]
            if not os.path.isfile(font_path):
                self.send_error('NOT EXIST')
            shutil.copy(font_path, '/usr/share/fonts/truetype/temp')
            self.send_ok()

        def cmd_upload_to(self, params):
            params = params.split(' ')
            file_size = int(params[0])
            file_path = params[1]

            def upload_callback(buf):
                dirs = file_path.rsplit('/', 1)[0]
                if not os.path.exists(dirs):
                    os.makedirs(dirs)
                with open(file_path, 'wb') as f:
                    f.write(buf)
                self.send_ok()

            def progress_callback(progress):
                self.send_json(status='progress', progress=progress)

            helper = BinaryUploadHelper(int(file_size), upload_callback, progress_callback=progress_callback)
            self.set_binary_helper(helper)
            self.send_json(status='continue')

    return UtilsApi
