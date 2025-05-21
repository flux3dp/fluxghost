from fluxghost.api.fcode_reader import fcode_reader_api_mixin

from .base import WebSocketBase


class WebsocketFcodeReader(fcode_reader_api_mixin(WebSocketBase)):
    pass
