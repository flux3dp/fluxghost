
from fluxghost.api.pen_svg_parser import pen_svg_parser_api_mixin
from .base import MixedWebsocketBase


class WebsocketPenSvgParser(pen_svg_parser_api_mixin(MixedWebsocketBase)):
    pass
