import logging
import platform
import socket
import ssl
from os import getenv, path
from select import select
from sys import stdout
from threading import Lock

from fluxghost.cert import CERT_DIR
from fluxghost.http_handlers.file_handler import FileHandler
from fluxghost.http_handlers.websocket_handler import WebSocketHandler

logger = logging.getLogger('HTTPServer')

certfile = path.join(CERT_DIR, 'fullchain.pem')
keyfile = path.join(CERT_DIR, 'privkey.pem')


class HttpServerBase:
    runmode = None
    discover_mutex = None
    discover = None

    def __init__(
        self, assets_path, address, allow_foreign=False, enable_discover=False, backlog=10, debug=False, ssl_port=8443
    ):
        self.discover_mutex = Lock()
        self.assets_handler = FileHandler(assets_path)
        self.ws_handler = WebSocketHandler()
        self.enable_discover = enable_discover
        self.discover_devices = {}
        self.debug = debug
        self.allow_foreign = allow_foreign
        self.push_studio_ws = None

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(address)
        self.sock.listen(backlog)

        self.ssl_sock = None
        if path.isfile(certfile) and path.isfile(keyfile):
            try:
                ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                ctx.load_cert_chain(certfile, keyfile)
                raw_ssl_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                raw_ssl_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                raw_ssl_sock.bind((address[0], ssl_port))
                raw_ssl_sock.listen(backlog)
                self.ssl_sock = ctx.wrap_socket(raw_ssl_sock, server_side=True)
                logger.info('Listen HTTPS on %s:%s' % (address[0], ssl_port))
            except Exception:
                logger.exception('Failed to start SSL socket')
                self.ssl_sock = None
        else:
            logger.info('SSL cert not found, skipping HTTPS')

        if address[1] == 0:
            address = self.sock.getsockname()
            home = str(path.expanduser('~'))
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

            with open(appdata, 'w') as portFile:
                portFile.write(str(address[1]))

        stdout.write('{"type": "ready", "port": %i}\n' % address[1])
        stdout.flush()

        from fluxclient import __version__ as client_version
        from fluxghost import __version__ as ghost_version

        logger.info('fluxghost: %s, fluxclient: %s', ghost_version, client_version)

        logger.info('Listen HTTP on %s:%s' % address)

        self.discover_devices = {}

        if debug:
            from fluxghost.simulate import SimulateDevice

            self.simulate_device = s = SimulateDevice()
            self.discover_devices[s.uuid] = s

        try:
            self.launch_discover()
        except OSError:
            logger.exception('Can not start discover service')

    def launch_discover(self):
        from fluxclient.device.discover import DeviceDiscover

        self.discover = DeviceDiscover()
        self.discover_socks = self.discover.socks

    def _build_select_sockets(self):
        sockets = (self.sock,)
        if self.ssl_sock:
            sockets += (self.ssl_sock,)
        if self.discover:
            sockets += self.discover_socks
        return sockets

    def serve_forever(self):
        self.running = True
        disc = self.discover
        sockets = self._build_select_sockets()
        args = (sockets, (), (), 5.0)

        while self.running:
            try:
                if disc is None:
                    try:
                        self.launch_discover()
                        disc = self.discover
                        sockets = self._build_select_sockets()
                        args = (sockets, (), (), 30.0)
                        logger.info('Discover started')
                    except OSError:
                        pass

                try:
                    for device in disc.tcp_devices:
                        self.on_discover_device(disc, device.uuid, device)
                except Exception as e:
                    logger.error('Get tcp devices error {}'.format(e))

                for sock in select(*args)[0]:
                    if sock == self.sock:
                        self.on_accept(self.sock)
                    elif sock == self.ssl_sock:
                        self.on_accept(self.ssl_sock)
                    elif sock in disc.socks:
                        try:
                            disc.try_receive(disc.socks, callback=self.on_discover_device, timeout=0.01)
                        except OSError:
                            logger.debug('Discover error, recreate')

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
