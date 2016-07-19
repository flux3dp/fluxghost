
from threading import Lock
from select import select
import logging
import socket

from fluxghost.http_handlers.websocket_handler import WebSocketHandler
from fluxghost.http_handlers.file_handler import FileHandler

logger = logging.getLogger("HTTPServer")


class HttpServerBase(object):
    runmode = None
    discover_mutex = None

    def __init__(self, assets_path, address, allow_foreign=False,
                 allow_origin='127.0.0.1', enable_discover=False, backlog=10, debug=False):
        self.discover_mutex = Lock()
        self.assets_handler = FileHandler(assets_path)
        self.ws_handler = WebSocketHandler()
        self.enable_discover = enable_discover
        self.discover_devices = {}
        self.debug = debug
        self.allow_foreign = allow_foreign
        self.allow_origin = allow_origin

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

        if debug:
            from fluxghost.simulate import SimulateDevice
            self.simulate_device = s = SimulateDevice()
            self.discover_devices[s.uuid] = s

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

    def on_discover_device(self, discover_instance, uuid, device, **kw):
        with self.discover_mutex:
            if uuid not in self.discover_devices:
                self.discover_devices[uuid] = device
