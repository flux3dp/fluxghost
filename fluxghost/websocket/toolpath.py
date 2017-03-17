
from fluxghost.api.bitmap_toolpath import laser_bitmap_api_mixin
from fluxghost.api.svg_toolpath import (laser_svg_api_mixin,
                                        vinyl_svg_api_mixin)
from .base import WebSocketBase


class WebsocketLaserBitmap(laser_bitmap_api_mixin(WebSocketBase)):
    pass


class WebsocketLaserSvg(laser_svg_api_mixin(WebSocketBase)):
    pass


class WebsocketVinylSvg(vinyl_svg_api_mixin(WebSocketBase)):
    pass
