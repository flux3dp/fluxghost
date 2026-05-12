import logging
import ssl
import threading

from fluxghost.http_handler import HttpHandler
from fluxghost.http_server_base import HttpServerBase

logger = logging.getLogger('HTTPServer')


class HttpServer(HttpServerBase):
    runmode = 'THREAD'

    def on_accept(self, sock):
        try:
            request, client = sock.accept()
        except ssl.SSLError as e:
            logger.error('SSL Accept error: %s' % e)
            return
        except Exception as e:
            logger.error('Accept error: %s' % e)
            return

        w = threading.Thread(target=HttpHandler, args=(request, client, self))
        w.setDaemon(True)
        w.start()
