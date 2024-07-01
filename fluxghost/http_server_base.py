
from threading import Lock
from select import select
import logging
import socket
from sys import stdout
import platform
from os import getenv, path

from fluxghost.http_handlers.websocket_handler import WebSocketHandler
from fluxghost.http_handlers.file_handler import FileHandler

logger = logging.getLogger("HTTPServer")


class HttpServerBase(object):
    runmode = None
    discover_mutex = None
    discover = None

    def __init__(self, assets_path, address, allow_foreign=False,
                 enable_discover=False, backlog=10, debug=False):
        self.discover_mutex = Lock()
        self.assets_handler = FileHandler(assets_path)
        self.ws_handler = WebSocketHandler()
        self.enable_discover = enable_discover
        self.discover_devices = {}
        self.debug = debug
        self.allow_foreign = allow_foreign
        self.push_studio_ws = None

        self.sock = s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(address)
        s.listen(backlog)
        if address[1] == 0:
            address = s.getsockname()
            home = str(path.expanduser("~"))
            sys = platform.system()
            appdata = ''

            if sys == 'Darwin':
                appdata = path.join(home, 'Library', 'Application Support')
            elif sys == 'Windows':
                try:
                    appdata = getenv('APPDATA')
                except Exception:
                    appdata = None
                if not appdata:
                    appdata = path.join(home, 'AppData', 'Roaming')
            elif sys == 'Linux':
                appdata = path.join(home, '.config')
            else:
                appdata = path.join(home, '.config')

            appdata = path.join(appdata, 'FluxStudioPort')

            portFile = open(appdata, 'w')
            portFile.write(str(address[1]))
            portFile.close()

        stdout.write('{"type": "ready", "port": %i}\n' % address[1])
        stdout.flush()

        from fluxghost import __version__ as ghost_version
        from fluxclient import __version__ as client_version
        logger.info("fluxghost: %s, fluxclient: %s", ghost_version,
                    client_version)

        logger.info("Listen HTTP on %s:%s" % address)

        self.discover_devices = {}

        if debug:
            from fluxghost.simulate import SimulateDevice
            self.simulate_device = s = SimulateDevice()
            self.discover_devices[s.uuid] = s

        try:
            self.launch_discover()
        except OSError:
            logger.exception("Can not start discover service")

    def launch_discover(self):
        from fluxclient.device.discover import DeviceDiscover
        self.discover = DeviceDiscover()
        self.discover_socks = self.discover.socks

    def serve_forever(self):
        self.running = True
        disc = self.discover
        if disc:
            args = ((self.sock, ) + self.discover_socks, (), (), 5.)
        else:
            args = ((self.sock, ), (), (), 5.)

        while self.running:
            try:
                if disc is None:
                    try:
                        self.launch_discover()
                        disc = self.discover
                        args = ((self.sock, ) + self.discover_socks, (), (),
                                30.)
                        logger.info("Discover started")
                    except OSError:
                        pass

                try:
                    for device in disc.tcp_devices:
                        self.on_discover_device(disc, device.uuid, device)
                except Exception as e:
                    logger.error('Get tcp devices error {}'.format(e))

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

    def set_push_studio_ws(self, ws):
        self.push_studio_ws = ws
