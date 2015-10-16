# !/usr/bin/env python3

import logging
import sys

from fluxghost.websocket.laser_svg_parser import WebsocketLaserSvgParser
from fluxclient.laser.pen_draw import PenDraw

logger = logging.getLogger("WS.Pen Draw")

MODE_PRESET = "preset"
MODE_MANUALLY = "manually"


class WebsocketPenDraw(WebsocketLaserSvgParser):
    self._m_pen_draw = None

    @property
    def m_laser_svg(self):
        return self.m_pen_draw

    @property
    def m_pen_draw(self):
        if self._m_pen_draw is None:
            self._m_pen_draw = PenDraw()
        return self.m_pen_draw
