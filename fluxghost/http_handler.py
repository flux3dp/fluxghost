
import os
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse
from urllib.request import Request
from urllib.request import urlopen
import logging

from fluxghost.http_websocket_route import get_match_ws_service
from fluxghost import __version__
from io import StringIO
import urllib.error

logger = logging.getLogger("HTTP")


class HttpHandler(BaseHTTPRequestHandler):
    server_version = "FLUXGhost/%s" % __version__
    protocol_version = "HTTP/1.1"

    def __init__(self, request, client, server):
        request.settimeout(60.)
        try:
            BaseHTTPRequestHandler.__init__(self, request, client, server)
        except OSError as e:
            if server.debug:
                logger.exception("OSError in http request")
            else:
                logger.error("%s", e)
        except Exception:
            logger.exception("Unhandle Error")

    def version_string(self):
        return self.server_version

    def log_error(self, format, *args):
        self.log_message(format, *args, error=True)

    def log_message(self, format, *args, **kw):
        if kw.get("error"):
            logger.warn("%s %s" % (self.address_string(), format % args))
        else:
            logger.info("%s %s" % (self.address_string(), format % args))

    def do_GET(self):  # noqa
        if self.path.startswith("/ws/"):
            klass, kwargs = get_match_ws_service(self.path[4:])

            if klass:
                self.serve_websocket(klass, kwargs)
            else:
                logger.exception("Websocket route error: %s" % self.path[4:])
                self.response_404()

        elif self.path == "/":
            return self.serve_assets("index.html")
        elif self.path.startswith("/api"):
            try:
                hostname = os.environ.get("proxy_api_host")
                print("Proxying %s" % hostname)
                url = 'http://{}{}'.format(hostname, self.path)
                req = Request(url=url)
                req_headers = self.headers.items()
                for header, value in req_headers:
                    if str(header).startswith("Host"):
                        continue
                    if str(header).startswith("Accept-Encoding"):
                        continue
                    req.add_header(header, value)
                try:
                    resp = urlopen(req)
                except urllib.error.HTTPError as e:
                    if e.getcode():
                        resp = e
                    else:
                        self.send_error(599, u'error proxying: {}'.format(unicode(e)))
                        return
                self.send_response(resp.getcode())
                respheaders = resp.getheaders()
                for header, value in respheaders:
                    if str(header).startswith("Transfer-Encoding"):
                        continue
                    self.send_header(header, value)
                self.end_headers()
                resp_content = resp.read(4192)
                while resp_content:
                    self.wfile.write(resp_content)
                    resp_content = resp.read(4192)
                self.wfile.flush()
            except IOError as e:
                self.send_error(404, 'error trying to proxy: {}'.format(str(e)))
        else:
            #self.send_response(200)
            #self.end_headers()
            #self.wfile.write('sadvd'.encode('utf-8'))
            #logger.error("all sent2 %d " % len('sadvd'))
            self.serve_assets(self.path[1:])

    def do_POST(self):
        hostname = os.environ.get("proxy_api_host")
        print("Proxying %s" % hostname)
        url = 'http://{}{}'.format(hostname, self.path)
        req = Request(url=url)
        req_headers = self.headers.items()
        data_length = 0
        print("Getting headers")
        for header, value in req_headers:
            if str(header).startswith("Host"):
                continue
            if str(header).startswith("Accept-Encoding"):
                continue
            if header == "Content-Length":
                data_length = int(value) if value else 0
            req.add_header(header, value)

        print("Reading request %d" % data_length)
        request_data = self.rfile.read(data_length)
        print("Generating request")
        try:
            resp = urlopen(req, data=request_data)
            print("Response generated")
        except urllib.error.HTTPError as e:
            if e.getcode():
                resp = e
                print("Response Error code " + str(e.getcode()))
            else:
                print("Something went wrong..")
                self.send_error(599, u'error proxying: {}'.format(unicode(e)))
                return
        print("Proxy response code %d" % resp.getcode())
        self.send_response(resp.getcode())
        respheaders = resp.getheaders()
        for header, value in respheaders:
            if str(header).startswith("Transfer-Encoding"):
                continue
            #print(self.path + " RESPH: " + header + " vs " + value)
            self.send_header(header, value)
        self.send_header("Access-Control-Allow-Origin", "*")
        print(self.path + " end headers")
        self.end_headers()
        data = resp.read();
        print(self.path + " response readed")
        self.wfile.write(data)
        self.wfile.flush()
        print(self.path + " flushed")

    def serve_assets(self, path):
        self.server.assets_handler.handle_request(self, path)

    def serve_websocket(self, ws_class, kwargs):
        if not self.server.allow_foreign and "Origin" in self.headers:
            url = urlparse(self.headers["Origin"])
            if url.scheme in ("chrome-extension", "file"):
                pass
            elif url.hostname not in ('127.0.0.1', '127.0.0.1'):
                logger.error("Bad websocket request from %s",
                             self.headers["Origin"])
                self.response_404()
                return

        if self.server.ws_handler.handle_request(self):
            client = self.address_string()
            module = ws_class.__name__

            logger.debug("%s:%s connected" % (client, module))
            ws = ws_class(self.request, client, self.server, self.path,
                          **kwargs)
            if self.path.find('push-studio') != -1: 
                self.server.set_push_studio_ws(ws)
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
