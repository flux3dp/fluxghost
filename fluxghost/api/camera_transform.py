import io
import logging

import cv2
import numpy as np
from PIL import Image

from .fisheye_camera_mixin import FisheyeCameraMixin
from .misc import BinaryUploadHelper, BinaryHelperMixin, OnTextMessageMixin


logger = logging.getLogger(__file__)


def camera_transform_api_mixin(cls):
    class CameraTransformApi(FisheyeCameraMixin, OnTextMessageMixin, BinaryHelperMixin, cls):
        def __init__(self, *args, **kw):
            super(CameraTransformApi, self).__init__(*args, **kw)
            self.reset_params()
            if hasattr(self, 'cmd_mapping'):
                self.cmd_mapping.update({
                    'transform_image': [self.transform_image],
                })
            else:
                self.cmd_mapping = {
                    'transform_image': [self.transform_image],
                }

        def transform_image(self, *params):
            def upload_callback(buf):
                image = Image.open(io.BytesIO(buf))
                if self.fisheye_param is not None:
                    try:
                        cv_img = np.array(image)
                        cv_img = cv2.cvtColor(cv_img, cv2.COLOR_RGBA2BGR)
                    except Exception:
                        self.send_binary(image)
                        return
                    img = self.handle_fisheye_image(cv_img, downsample=1)
                    _, array_buffer = cv2.imencode('.jpg', img)
                    img_bytes = array_buffer.tobytes()
                    self.send_binary(img_bytes)
                else:
                    self.send_binary(image)
            file_length = int(params[0])
            helper = BinaryUploadHelper(int(file_length), upload_callback)
            self.set_binary_helper(helper)
            self.send_json(status='continue')


    return CameraTransformApi
