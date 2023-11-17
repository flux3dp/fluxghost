import base64
import io
import logging
import os
import shutil
import subprocess
import tempfile

from PIL import Image, ImageCms

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
                'rgb_to_cmyk': [self.rgb_to_cmyk],
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
                    proc = subprocess.Popen(['pdf2svg', temp_pdf.name, temp_svg.name])
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

        def rgb_to_cmyk(self, params):
            params = params.split(' ')

            def upload_callback(buf):
                image = Image.open(io.BytesIO(buf))
                self.send_json(status='uploaded')
                if image.mode == 'RGBA':
                    white_image = Image.new('RGBA', image.size, 'white')
                    image = Image.alpha_composite(white_image, image)

                srgb_profile = ImageCms.createProfile('sRGB')
                cmyk_profile = ImageCms.getOpenProfile('static/Coated_Fogra39L_VIGC_300.icc')
                transform = ImageCms.buildTransform(srgb_profile, cmyk_profile, 'RGB', 'CMYK')
                image = ImageCms.applyTransform(image, transform)
                image = image.convert('RGB')
                out_byte = io.BytesIO()
                image.save(out_byte, format='JPEG', quality=100, subsampling=0)
                image_binary = out_byte.getvalue()
                result_type = params[1]
                if result_type == 'base64':
                    base64_data = base64.b64encode(image_binary).decode('utf-8')
                    self.send_ok(data=base64_data)
                else:
                    self.send_json(status="complete", length=len(image_binary))
                    self.send_binary(out_byte.getvalue())

            file_length = int(params[0])
            helper = BinaryUploadHelper(int(file_length), upload_callback)
            self.set_binary_helper(helper)
            self.send_json(status='continue')

    return UtilsApi
