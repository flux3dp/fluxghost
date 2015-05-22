
from fluxghost.websocket.control import WebsocketControl
from fluxghost.websocket.discover import WebsocketDiscover
from fluxghost.websocket.echo import WebsocketEcho
from fluxghost.websocket.file import WebsocketFile
from fluxghost.websocket.laser_bitmap_parser import WebsocketLaserBitmapParser
from fluxghost.websocket.laser_parser import WebsocketLaserParser
from fluxghost.websocket.scan_modeling import Websocket3DScannModeling
from fluxghost.websocket.scan_control import Websocket3DScanControl


SERVICES = [WebsocketEcho,
            WebsocketFile,
            WebsocketLaserBitmapParser,
            WebsocketLaserParser,
            Websocket3DScannModeling,
            Websocket3DScanControl,
            WebsocketControl,
            WebsocketDiscover]


def get_match_ws_service(path):
    for klass in SERVICES:
        if klass.match_route(path):
            return klass
