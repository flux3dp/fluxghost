
import re

from fluxghost.websocket.echo import WebsocketEcho
from fluxghost.websocket.file import WebsocketFile
from fluxghost.websocket.config import WebsocketConfig
from fluxghost.websocket.scan_modeling import Websocket3DScannModeling
from fluxghost.websocket.laser_bitmap_parser import WebsocketLaserBitmapParser
from fluxghost.websocket.laser_svg_parser import WebsocketLaserSvgParser
from fluxghost.websocket.stl_slicing_parser import Websocket3DSlicing


from fluxghost.websocket.discover import WebsocketDiscover
from fluxghost.websocket.touch import WebsocketTouch
from fluxghost.websocket.control import WebsocketControl
from fluxghost.websocket.scan_control import Websocket3DScanControl
from fluxghost.websocket.scan_control import SimulateWebsocket3DScanControl
from fluxghost.websocket.usb_config import WebsocketUsbConfig


ROUTES = [
    (re.compile("echo"), WebsocketEcho),
    (re.compile("file"), WebsocketFile),
    (re.compile("config"), WebsocketConfig),
    (re.compile("3d-scan-modeling"), Websocket3DScannModeling),
    (re.compile("bitmap-laser-parser"), WebsocketLaserBitmapParser),
    (re.compile("svg-laser-parser"), WebsocketLaserSvgParser),

    # Simulate
    (re.compile("3d-scan-control/(?P<serial>[1]{25})"),
     SimulateWebsocket3DScanControl),

    (re.compile("discover"), WebsocketDiscover),
    (re.compile("touch"), WebsocketTouch),
    (re.compile("control/(?P<serial>[0-9A-Z]{25})"), WebsocketControl),
    (re.compile("3dprint-slicing"), Websocket3DSlicing),
    (re.compile("3d-scan-control/(?P<serial>[0-9A-Z]{25})"),
     Websocket3DScanControl),
    (re.compile("usb-config"), WebsocketUsbConfig)]


def get_match_ws_service(path):
    for exp, klass in ROUTES:
        match = exp.match(path)
        if match:
            return klass, match.groupdict()
    return None, None
