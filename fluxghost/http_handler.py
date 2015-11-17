
from http.server import BaseHTTPRequestHandler
import logging

logger = logging.getLogger("HTTP")

from fluxghost.http_websocket_route import get_match_ws_service
from fluxghost import __version__


class HttpHandler(BaseHTTPRequestHandler):
    server_version = "FLUXGhost/%s" % __version__
    protocol_version = "HTTP/1.1"

    def __init__(self, request, client, server):
        try:
            request.settimeout(60.)
            BaseHTTPRequestHandler.__init__(self, request, client, server)
        except Exception:
            logger.exception("Unhandle Error")

    def version_string(self):
        return self.server_version

    def log_error(self, format, *args):
        self.log_message(format, *args, error=True)

    def log_message(self, format, *args, **kw):
        if kw.get("error"):
            logger.error("%s %s" % (self.address_string(), format % args))
        else:
            logger.info("%s %s" % (self.address_string(), format % args))

    def do_GET(self):
        if self.path.startswith("/ws/"):
            klass, kwargs = get_match_ws_service(self.path[4:])

            if klass:
                self.serve_websocket(klass, kwargs)
            else:
                logger.exception("Websocket route error: %s" % self.path[4:])
                self.response_404()

        elif self.path == "/":
            self.serve_assets("index.html")
        else:
            self.serve_assets(self.path[1:])

    def serve_assets(self, path):
        self.server.assets_handler.handle_request(self, path)

    def serve_websocket(self, ws_class, kwargs):
        if self.server.ws_handler.handle_request(self):
            client = self.address_string()
            module = ws_class.__name__

            logger.debug("%s:%s connected" % (client, module))
            ws = ws_class(self.request, client, self.server, self.path,
                          **kwargs)
            ws.serve_forever()
            logger.debug("%s:%s disconnected" % (client, module))

    def response(self, code, message, body):
        buf = body.encode()

        self.send_response(code, message)
        self.send_header('Content-Type', 'text/plain; charset=UTF-8')
        self.send_header('Content-Length', len(buf))
        if not self.close_connection:
            self.send_header('Connection', 'Keep-Alive')
        self.end_headers()
        self.wfile.write(bytes(buf))

    def response_403(self, message="Forbidden", body="Forbidden"):
        self.response(403, message, body)

    def response_404(self, message="Not Found", body="Not Found"):
        self.response(404, message, body)
