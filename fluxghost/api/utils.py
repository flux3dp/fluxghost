import logging
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

    return UtilsApi
