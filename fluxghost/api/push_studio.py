import logging
import io
import numpy as np
import copy
import socket

from .misc import BinaryUploadHelper, BinaryHelperMixin, OnTextMessageMixin

logger = logging.getLogger("API.PUSH_STUDIO")

def push_studio_api_mixin(cls):
    class PushStudioApi(OnTextMessageMixin, BinaryHelperMixin, cls):

        def __init__(self, *args, **kw):
            super(PushStudioApi, self).__init__(*args, **kw)

    return PushStudioApi
