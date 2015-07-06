
from multiprocessing import Process
import sys


from fluxghost.http_server_base import HttpServerBase, logger


def fork_entry(request, client, server):
    from fluxghost.http_handler import HttpHandler
    HttpHandler(request, client, server)


def check_autoreload():
    if "fluxghost.http_handler" in sys.modules:
        logger.error("Warning!! The fluxghost.http_handler has been "
                     "loaded before fork, auto-reload moudle function is"
                     " not work anymore.")
        return
    if "fluxclient" in sys.modules:
        logger.error("Warning!! The fluxclient has been "
                     "loaded before fork, auto-reload moudle function is"
                     " not work anymore.")
        return


class HttpServer(HttpServerBase):
    def on_accept(self):
        check_autoreload()
        request, client = self.sock.accept()

        w = Process(target=fork_entry, args=(request, client, self))
        w.daemon = True
        w.start()

        request.close()
