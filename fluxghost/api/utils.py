import base64
import io
import logging
import os
import shutil
import subprocess
import tempfile

import cv2
import numpy as np
from PIL import Image, ImageCms

from fluxghost.utils.contour import find_similar_contours
from fluxghost.utils.opencv import findContours

from .misc import BinaryHelperMixin, BinaryUploadHelper, OnTextMessageMixin

logger = logging.getLogger('API.UTILS')


# General utility api
def utils_api_mixin(cls):
    class UtilsApi(OnTextMessageMixin, BinaryHelperMixin, cls):
        def __init__(self, *args, **kw):
            super().__init__(*args, **kw)
            self.cmd_mapping = {
                'pdf2svg': [self.cmd_pdf2svg],
                'upload_to': [self.cmd_upload_to],
                'select_font': [self.cmd_select_font],
                'check_exist': [self.cmd_check_exist],
                'rgb_to_cmyk': [self.rgb_to_cmyk],
                'split_color': [self.split_color],
                'get_similar_contours': [self.get_similar_contours],
                'get_all_similar_contours': [self.get_all_similar_contours],
                'get_convex_hull': [self.get_convex_hull],
            }

        def cmd_pdf2svg(self, params):
            params = params.split(' ')
            file_size = int(params[0])

            def upload_callback(buf):
                with tempfile.NamedTemporaryFile() as temp_pdf, tempfile.NamedTemporaryFile() as temp_svg:
                    temp_pdf.write(buf)
                    temp_pdf.seek(0)
                    try:
                        proc = subprocess.Popen(['pdf2svg', temp_pdf.name, temp_svg.name])
                        ret = proc.wait()

                        temp_svg.seek(0)
                        svg_content = temp_svg.read()
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
                if image.mode != 'CMYK':
                    if image.info.get('transparency', None) is not None:
                        image = image.convert('RGBA')
                    if image.mode == 'RGBA':
                        white_image = Image.new('RGBA', image.size, 'white')
                        image = Image.alpha_composite(white_image, image)
                    image = image.convert('RGB')
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
                    self.send_json(status='complete', length=len(image_binary))
                    self.send_binary(out_byte.getvalue())

            file_length = int(params[0])
            helper = BinaryUploadHelper(int(file_length), upload_callback)
            self.set_binary_helper(helper)
            self.send_json(status='continue')

        def split_color(self, params):
            params = params.split(' ')
            color_type = params[1]

            def upload_callback(buf):
                image = Image.open(io.BytesIO(buf))
                self.send_json(status='uploaded')
                if image.mode != 'CMYK':
                    if image.info.get('transparency', None) is not None:
                        image = image.convert('RGBA')
                    if image.mode == 'RGBA':
                        white_image = Image.new('RGBA', image.size, 'white')
                        image = Image.alpha_composite(white_image, image)
                    image = image.convert('RGB')
                    if color_type == 'cmyk':
                        image = image.convert('CMYK')
                    else:
                        srgb_profile = ImageCms.createProfile('sRGB')
                        cmyk_profile = ImageCms.getOpenProfile('static/Coated_Fogra39L_VIGC_300.icc')
                        transform = ImageCms.buildTransform(srgb_profile, cmyk_profile, 'RGB', 'CMYK')
                        image = ImageCms.applyTransform(image, transform)
                c, m, y, k = image.split()
                c = Image.eval(c, lambda x: 255 - x)
                m = Image.eval(m, lambda x: 255 - x)
                y = Image.eval(y, lambda x: 255 - x)
                k = Image.eval(k, lambda x: 255 - x)

                def get_base64(image: Image):
                    out_byte = io.BytesIO()
                    image.save(out_byte, format='JPEG', quality=100, subsampling=0)
                    image_binary = out_byte.getvalue()
                    return base64.b64encode(image_binary).decode('utf-8')

                c = get_base64(c)
                m = get_base64(m)
                y = get_base64(y)
                k = get_base64(k)
                self.send_ok(c=c, m=m, y=y, k=k)

            file_length = int(params[0])
            helper = BinaryUploadHelper(int(file_length), upload_callback)
            self.set_binary_helper(helper)
            self.send_json(status='continue')

        def get_similar_contours(self, params):
            params = params.split(' ')

            def upload_callback(buf):
                try:
                    image = Image.open(io.BytesIO(buf))
                    cv_img = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
                    is_spliced_img = False
                    if len(params) > 1 and params[1] == '1':
                        is_spliced_img = True
                    data = find_similar_contours(cv_img, is_spliced_img)
                    self.send_ok(data=data)
                except Exception as e:
                    logger.exception('Error in get_similar_contours')
                    self.send_json(status='error', info=str(e))

            file_length = int(params[0])
            helper = BinaryUploadHelper(int(file_length), upload_callback)
            self.set_binary_helper(helper)
            self.send_json(status='continue')

        def get_all_similar_contours(self, params):
            params = params.split(' ')

            def upload_callback(buf):
                try:
                    image = Image.open(io.BytesIO(buf))
                    cv_img = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
                    is_spliced_img = False
                    if len(params) > 1 and params[1] == '1':
                        is_spliced_img = True
                    data = find_similar_contours(cv_img, is_spliced_img, all_groups=True)
                    self.send_ok(data=data)
                except Exception as e:
                    logger.exception('Error in get_all_similar_contours')
                    self.send_json(status='error', info=str(e))

            file_length = int(params[0])
            helper = BinaryUploadHelper(int(file_length), upload_callback)
            self.set_binary_helper(helper)
            self.send_json(status='continue')

        def get_convex_hull(self, params):
            params = params.split(' ')

            def upload_callback(buf):
                try:
                    image = Image.open(io.BytesIO(buf))
                    cv_img = cv2.cvtColor(np.array(image), cv2.COLOR_RGBA2GRAY)
                    cv_img = cv2.threshold(cv_img, 252, 255, cv2.THRESH_BINARY_INV)[1]
                    contours = findContours(cv_img, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0]
                    if len(contours) == 0:
                        self.send_ok(data=[])
                        return
                    combined = np.vstack([c for c in contours])
                    convex_hull = cv2.convexHull(combined)
                    convex_hull_points = convex_hull.reshape(-1, 2)
                    dists = np.linalg.norm(convex_hull_points, axis=1)
                    convex_hull_points = np.roll(convex_hull_points, -np.argmin(dists), axis=0)
                    self.send_ok(data=convex_hull_points.tolist())
                except Exception as e:
                    logger.exception('Error in get_convex_hull')
                    self.send_json(status='error', info=str(e))

            file_length = int(params[0])
            helper = BinaryUploadHelper(int(file_length), upload_callback)
            self.set_binary_helper(helper)
            self.send_json(status='continue')

    return UtilsApi
