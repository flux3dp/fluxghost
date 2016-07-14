
from fluxghost.api.laser_bitmap_parser import laser_bitmap_parser_api_mixin
from .base import WebsocketBase


class WebsocketLaserBitmapParser(
        laser_bitmap_parser_api_mixin(WebsocketBase)):
    pass
