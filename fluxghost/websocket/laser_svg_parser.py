
from fluxghost.api.laser_svg_parser import laser_svg_parser_api_mixin
from .base import WebSocketBase


class WebsocketLaserSvgParser(laser_svg_parser_api_mixin(WebSocketBase)):
    pass
