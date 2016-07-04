# !/usr/bin/env python3

from fluxghost.api.fcode_reader import fcode_reader_api_mixin
from .base import MixedWebsocketBase


class WebsocketFcodeReader(fcode_reader_api_mixin(MixedWebsocketBase)):
    pass
