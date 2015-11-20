
import threading

from fluxghost.http_server_base import HttpServerBase
from fluxghost.http_handler import HttpHandler


class HttpServer(HttpServerBase):
    runmode = "THREAD"

    def on_accept(self):
        request, client = self.sock.accept()

        w = threading.Thread(target=HttpHandler, args=(request, client, self))
        w.setDaemon(True)
        w.start()
