
from select import select
from time import time
import logging
import socket

from fluxghost.http_handlers.websocket_handler import WebSocketHandler
from fluxghost.http_handlers.file_handler import FileHandler

logger = logging.getLogger("HTTPServer")


class HttpServerBase(object):
    runmode = None

    def __init__(self, assets_path, address, enable_discover=False,
                 backlog=10):
        self.assets_handler = FileHandler(assets_path)
        self.ws_handler = WebSocketHandler()
        self.enable_discover = enable_discover
        self.discover_devices = {}

        self.sock = s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(address)
        s.listen(backlog)

        if address[1] == 0:
            from sys import stdout
            address = s.getsockname()
            stdout.write("LISTEN ON %i\n" % address[1])
            stdout.flush()

        logger.info("Listen HTTP on %s:%s" % address)

        self.discover_devices = {}
        self.launch_discover()

    def launch_discover(self):
        from fluxclient.upnp.discover import UpnpDiscover
        self.discover = UpnpDiscover()
        self.discover_socks = self.discover.socks

    def serve_forever(self):
        self.running = True
        disc = self.discover
        args = ((self.sock, ) + self.discover_socks, (), (), 30.)

        while self.running:
            try:
                for sock in select(*args)[0]:
                    if sock == self.sock:
                        self.on_accept()
                    elif sock in disc.socks:
                        try:
                            disc.try_recive(
                                disc.socks,
                                callback=self.on_discover_device,
                                timeout=0.01)
                        except (OSError, socket.error):
                            logger.debug("Discover error, recreate")

            except InterruptedError:
                pass

            except KeyboardInterrupt:
                self.running = False

    def on_discover_device(self, discover_instance, **kw):
        uuid = kw["uuid"]
        kw["last_response"] = time()

        if uuid in self.discover_devices:
            exist = self.discover_devices[uuid]
            real_delta = exist["timedelta"]
            exist.update(kw)
            exist["timedelta"] = real_delta
        else:
            self.discover_devices[uuid] = kw
