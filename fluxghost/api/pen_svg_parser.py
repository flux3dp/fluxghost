
import logging

# from fluxghost.websocket.laser_svg_parser import WebsocketLaserSvgParser
from fluxclient.laser.pen_svg import PenSvg
from .laser_svg_parser import laser_svg_parser_api_mixin

logger = logging.getLogger("API.PEN.DRAW")

MODE_PRESET = "preset"
MODE_MANUALLY = "manually"


def pen_svg_parser_api_mixin(cls):
    class PenSvgParserApi(laser_svg_parser_api_mixin(cls)):
        _m_pen_draw = None

        def __init__(self, *args):
            super().__init__(*args)

        @property
        def m_laser_svg(self):
            return self.m_pen_draw

        @property
        def m_pen_draw(self):
            if self._m_pen_draw is None:
                self._m_pen_draw = PenSvg()
            return self._m_pen_draw
    return PenSvgParserApi
