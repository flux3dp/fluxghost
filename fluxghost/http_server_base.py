
from select import select
from time import time
import logging
import socket

logger = logging.getLogger("HTTPServer")

from fluxghost.http_handlers.websocket_handler import WebSocketHandler
from fluxghost.http_handlers.file_handler import FileHandler


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
        if enable_discover:
            from fluxclient.upnp.discover import UpnpDiscover
            self.discover = UpnpDiscover()
            self.discover_socks = self.discover.socks
        else:
            self.discover = None
            self.discover_socks = ()

    def serve_forever(self):
        self.running = True

        if self.enable_discover and self.runmode == "THREAD":
            logger.info("Run discover in background")
            from fluxclient.upnp.discover import UpnpDiscover
            disc = UpnpDiscover()
            args = ((self.sock, ) + disc.socks, (), (), 30.)
        else:
            args = ((self.sock, ), (), (), 30.)

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
                            disc = UpnpDiscover()
                            args = ((self.sock, ) + disc.socks, (), (), 30.)

            except InterruptedError:
                pass

    def on_discover_device(self, discover_instance, uuid, **kw):
        kw["last_response"] = time()
        if uuid not in self.discover_devices:
            kw["timedelta"] -= 100

        if uuid in self.discover_devices:
            exist = self.discover_devices[uuid]
            if exist["timedelta"] != kw["timedelta"]:
                kw["timedelta"] = exist["timedelta"]

        self.discover_devices[uuid] = kw
