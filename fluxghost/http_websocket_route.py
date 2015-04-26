
from fluxghost.websocket.laser_parser import WebsocketLaserParser
from fluxghost.websocket.discover import WebsocketDiscover
from fluxghost.websocket.echo import WebsocketEcho
from fluxghost.websocket.file import WebsocketFile


SERVICES = [WebsocketEcho,
            WebsocketFile,
            WebsocketLaserParser,
            WebsocketDiscover]

def get_match_ws_service(path):
    for klass in SERVICES:
        if klass.match_route(path):
            return klass
