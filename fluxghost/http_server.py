
from select import select
import threading
import logging
import socket
import os

logger = logging.getLogger("HTTPServer")

from fluxghost.http_handlers.websocket_handler import WebSocketHandler
from fluxghost.http_handlers.file_handler import FileHandler
from fluxghost.http_handler import HttpHandler


class HttpServer(object):
    def __init__(self, address, backlog=10, assets_path=None):
        self.assets_handler = FileHandler(
            os.path.join(os.path.dirname(__file__), "assets"))
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

    def on_accept(self):
        request, client = self.sock.accept()

        w = threading.Thread(target=HttpHandler, args=(request, client, self))
        w.setDaemon(True)
        w.start()
