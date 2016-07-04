
from fluxghost.api.laser_bitmap_parser import laser_bitmap_parser_api_mixin
from .base import MixedWebsocketBase


class WebsocketLaserBitmapParser(
        laser_bitmap_parser_api_mixin(MixedWebsocketBase)):
    pass
