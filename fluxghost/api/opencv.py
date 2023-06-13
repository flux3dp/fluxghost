import collections
import logging
import io

import cv2
import numpy as np
from PIL import Image

from .misc import BinaryUploadHelper, BinaryHelperMixin, OnTextMessageMixin

logger = logging.getLogger('API.OPEN_CV')


def opencv_mixin(cls):
    class OpenCVApi(OnTextMessageMixin, BinaryHelperMixin, cls):
        def __init__(self, *args, **kw):
            super(OpenCVApi, self).__init__(*args, **kw)
            self.cmd_mapping = {
                'upload': [self.cmd_upload_image],
                'sharpen': [self.cmd_sharpen],
            }
            self.imgs = {}
            self.imgs_history = collections.deque([])

        def update_history(self, img_url):
            try:
                self.imgs_history.remove(img_url)
            except ValueError:
                pass
            self.imgs_history.appendleft(img_url)
            if len(self.imgs_history) > 5:
                self.imgs_history.pop()

        def cmd_upload_image(self, params):
            params = params.split(' ')
            img_url = params[0]
            file_length = int(params[1])

            def upload_callback(buf):
                img = Image.open(io.BytesIO(buf))
                open_cv_img = np.array(img)
                open_cv_img = cv2.cvtColor(open_cv_img, cv2.COLOR_RGBA2BGRA)
                path = img_url.split('/')[-1]
                self.imgs[img_url] = open_cv_img
                self.update_history(img_url)
                self.send_ok()

            helper = BinaryUploadHelper(int(file_length), upload_callback)
            self.set_binary_helper(helper)
            self.send_json(status='continue')

        def cmd_sharpen(self, params):
            params = params.split(' ')
            img_url = params[0]
            sharpness = float(params[1])
            radius = int(params[2])
            if img_url not in self.imgs:
                return self.send_json(status='need_upload')
            open_cv_image = self.imgs[img_url]
            ksize = 2 * radius + 1
            logger.info('Sharpening img: {} with sharpness {}, radius {}'.format(
                img_url, sharpness, radius))
            gaussian_blur = cv2.GaussianBlur(open_cv_image, (ksize, ksize), 0)
            unsharp_img = cv2.addWeighted(
                open_cv_image, 1 + sharpness, gaussian_blur, -sharpness, 0)
            logger.info('Sharpen completed')
            is_success, array_buffer = cv2.imencode('.png', unsharp_img)
            img_bytes = array_buffer.tobytes()
            self.send_binary(img_bytes)

    return OpenCVApi
