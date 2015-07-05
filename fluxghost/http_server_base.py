
from select import select
import logging
import socket

logger = logging.getLogger("HTTPServer")

from fluxghost.http_handlers.websocket_handler import WebSocketHandler
from fluxghost.http_handlers.file_handler import FileHandler


class HttpServerBase(object):
    def __init__(self, assets_path, address, backlog=10):
        self.assets_handler = FileHandler(assets_path)
        self.ws_handler = WebSocketHandler()

        self.sock = s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(address)
        s.listen(backlog)
        logger.info("Listen HTTP on %s:%s" % address)

    def serve_forever(self):
        self.running = True

        args = ((self.sock, ), (), (), 30.)
        while self.running:
            rl = select(*args)[0]

            if rl:
                self.on_accept()
