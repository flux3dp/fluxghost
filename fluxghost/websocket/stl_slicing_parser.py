
from fluxghost.api.stl_slicing_parser import stl_slicing_parser_api_mixin
from .base import WebSocketBase


class Websocket3DSlicing(stl_slicing_parser_api_mixin(WebSocketBase)):
    pass
