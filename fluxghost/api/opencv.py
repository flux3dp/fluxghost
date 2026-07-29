import collections
import contextlib
import io
import json
import logging

import cv2
import numpy as np
from PIL import Image

from fluxghost.utils.camera.corner_detection.find_corners import find_blob_centers

from .misc import BinaryHelperMixin, BinaryUploadHelper, OnTextMessageMixin

logger = logging.getLogger('API.OPEN_CV')


def opencv_mixin(cls):
    class OpenCVApi(OnTextMessageMixin, BinaryHelperMixin, cls):
        def __init__(self, *args, **kw):
            super().__init__(*args, **kw)
            self.cmd_mapping = {
                'upload': [self.cmd_upload_image],
                'sharpen': [self.cmd_sharpen],
                'detect_blobs': [self.cmd_detect_blobs],
                'image_contour': [self.cmd_image_contour],
            }
            self.imgs = {}
            self.imgs_history = collections.deque([])

        def update_history(self, img_url):
            with contextlib.suppress(ValueError):
                self.imgs_history.remove(img_url)
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
                self.imgs[img_url] = open_cv_img
                self.update_history(img_url)
                self.send_ok()

            helper = BinaryUploadHelper(int(file_length), upload_callback)
            self.set_binary_helper(helper)
            self.send_json(status='continue')

        def cmd_detect_blobs(self, params):
            # detect_blobs <file_length> [<json_params>]
            # json_params: optional kwargs for find_blob_centers,
            # e.g. {"min_area": 100, "max_area": 1000, "min_circularity": 0.7}
            params = params.split(' ', 1)
            file_length = int(params[0])
            options = json.loads(params[1]) if len(params) > 1 and params[1].strip() else {}
            allowed_keys = (
                'min_threshold',
                'max_threshold',
                'min_area',
                'max_area',
                'min_circularity',
                'max_circularity',
                'min_convexity',
                'max_convexity',
            )
            kwargs = {key: options[key] for key in allowed_keys if key in options}

            def upload_callback(buf):
                img = Image.open(io.BytesIO(buf)).convert('RGB')
                open_cv_img = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
                logger.info('Detecting blobs with params: {}'.format(kwargs))
                centers = find_blob_centers(open_cv_img, **kwargs)
                logger.info('Detected {} blobs'.format(len(centers)))
                self.send_ok(points=[[float(x), float(y)] for x, y in centers])

            helper = BinaryUploadHelper(int(file_length), upload_callback)
            self.set_binary_helper(helper)
            self.send_json(status='continue')

        def cmd_image_contour(self, params):
            # image_contour <file_length> [<json_params>]
            # json_params: {"threshold": 250, "epsilon": 1.0, "min_area": 100, "alpha_threshold": 0}
            # Detects the outer silhouette of the image content (alpha channel when
            # present, otherwise dark-on-light with luminance < threshold) and returns
            # the outer contours in image pixel coordinates. Offsetting/smoothing the
            # outline is done client-side (Beam Studio runs a ClipperOffset on it).
            params = params.split(' ', 1)
            file_length = int(params[0])
            options = json.loads(params[1]) if len(params) > 1 and params[1].strip() else {}
            threshold = int(options.get('threshold', 250))
            epsilon = float(options.get('epsilon', 1.0))
            min_area = float(options.get('min_area', 100))
            # any non-zero coverage counts: thin strokes anti-alias to low alpha
            # and would vanish from the mask with a mid-range threshold
            alpha_threshold = int(options.get('alpha_threshold', 0))

            def upload_callback(buf):
                img = Image.open(io.BytesIO(buf)).convert('RGBA')
                arr = np.array(img)
                alpha = arr[:, :, 3]
                if (alpha < 255).any():
                    mask = (alpha > alpha_threshold).astype(np.uint8) * 255
                else:
                    gray = cv2.cvtColor(arr, cv2.COLOR_RGBA2GRAY)
                    mask = (gray < threshold).astype(np.uint8) * 255
                # pad so content touching the image border still closes its contour
                pad = 1
                mask = cv2.copyMakeBorder(mask, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=0)
                contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                result = []
                for contour in contours:
                    if cv2.contourArea(contour) < min_area:
                        continue
                    approx = cv2.approxPolyDP(contour, epsilon, True)
                    result.append([[float(point[0][0] - pad), float(point[0][1] - pad)] for point in approx])
                logger.info('Detected {} contours'.format(len(result)))
                self.send_ok(contours=result)

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
            logger.info('Sharpening img: {} with sharpness {}, radius {}'.format(img_url, sharpness, radius))
            gaussian_blur = cv2.GaussianBlur(open_cv_image, (ksize, ksize), 0)
            unsharp_img = cv2.addWeighted(open_cv_image, 1 + sharpness, gaussian_blur, -sharpness, 0)
            logger.info('Sharpen completed')
            _, array_buffer = cv2.imencode('.png', unsharp_img)
            img_bytes = array_buffer.tobytes()
            self.send_binary(img_bytes)

    return OpenCVApi
