
from fluxghost.api.laser_svg_parser import laser_svg_parser_api_mixin
from .base import MixedWebsocketBase


class WebsocketLaserSvgParser(laser_svg_parser_api_mixin(MixedWebsocketBase)):
    pass
