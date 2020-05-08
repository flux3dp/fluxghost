
import logging

logger = logging.getLogger('websocket.toolpath')

logger.info('Importing bitmap_toolpath')
from fluxghost.api.bitmap_toolpath import laser_bitmap_api_mixin
logger.info('Importing svgeditor_toolpath')
from fluxghost.api.svgeditor_toolpath import laser_svgeditor_api_mixin
logger.info('Importing svg_toolpath')
from fluxghost.api.svg_toolpath import (laser_svg_api_mixin,
                                        drawing_svg_api_mixin,
                                        vinyl_svg_api_mixin)
from .base import WebSocketBase


class WebsocketLaserBitmap(laser_bitmap_api_mixin(WebSocketBase)):
    pass


class WebsocketLaserSvg(laser_svg_api_mixin(WebSocketBase)):
    pass


class WebsocketLaserSvgeditor(laser_svgeditor_api_mixin(WebSocketBase)):
    pass


class WebsocketDrawingSvg(drawing_svg_api_mixin(WebSocketBase)):
    pass


class WebsocketVinylSvg(vinyl_svg_api_mixin(WebSocketBase)):
    pass
