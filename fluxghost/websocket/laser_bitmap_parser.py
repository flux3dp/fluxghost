
from fluxghost.api.laser_bitmap_parser import laser_bitmap_parser_api_mixin
from .base import WebSocketBase


class WebsocketLaserBitmapParser(
        laser_bitmap_parser_api_mixin(WebSocketBase)):
    pass
