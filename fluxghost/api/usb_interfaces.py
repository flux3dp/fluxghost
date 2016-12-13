
from threading import Thread
from glob import glob
import logging
import sys

from serial.tools import list_ports as _list_ports

from fluxclient.device.host2host_usb import USBProtocol, FluxUSBError
from fluxghost import g

logger = logging.getLogger("API.USB")


def h2h_usb_daemon_thread(protocol, address):
    logger.debug("USB daemon at %s start", address)
    g.USBDEVS[address] = protocol
    try:
        protocol.run()
        logger.debug("USB daemon at %s terminated", address)
    except Exception:
        logger.exception("USB daemon at %s crashed", address)

    g.USBDEVS.pop(address)
    protocol.close()


def usb_interfaces_api_mixin(cls):
    class ClosedUsbDev(object):
        endpoint_profile = False

    class H2HInterfacesApi(cls):
        def __init__(self, *args, **kw):
            super().__init__(*args, **kw)

        def on_text_message(self, message):
            if message == "list":
                self.list_devices()
            elif message.startswith("open "):
                addr = int(message[5:])
                self.open_device(addr)
            elif message.startswith("close "):
                addr = int(message[6:])
                self.close_device(addr)

        def on_binary_message(self, message):
            pass

        def on_close(self, message):
            pass

        def get_devices(self):
            usbdevs = {}
            ifces = USBProtocol.get_interfaces()
            for i in ifces:
                if i.address in g.USBDEVS:
                    usbdevs[i.address] = g.USBDEVS[i.address]
                else:
                    usbdevs[i.address] = None
            g.USBDEVS = usbdevs

        def list_devices(self):
            h2h = {ifce.address:
                   g.USBDEVS.get(ifce.address,
                                 ClosedUsbDev).endpoint_profile
                   for ifce in USBProtocol.get_interfaces()}

            if sys.platform.startswith('darwin'):
                uart = [s for s in glob('/dev/tty.*') if "Bl" not in s]
            else:
                uart = [s[0] for s in _list_ports.comports() if s[2] != "n/a"]

            self.send_ok(h2h=h2h, uart=uart)

        def open_device(self, addr):
            if g.USBDEVS.get(addr):
                self.send_error("RESOURCE_BUSY")
                return

            for usbdev in USBProtocol.get_interfaces():
                if usbdev.address == addr:
                    try:
                        usbprotocol = USBProtocol(usbdev)
                        t = Thread(target=h2h_usb_daemon_thread,
                                   args=(usbprotocol, addr))
                        t.daemon = True
                        t.start()
                        self.send_ok(devopen=addr,
                                     profile=usbprotocol.endpoint_profile)
                        logger.debug("USB address %s opened: %s", addr,
                                     usbprotocol.endpoint_profile)
                        return
                    except FluxUSBError as e:
                        self.send_error(e.symbol)
                        return
            self.send_error("NOT_FOUND")

        def close_device(self, addr):
            usbprotocol = g.USBDEVS.get(addr)
            if usbprotocol:
                usbprotocol.stop()
                self.send_ok(devclose=addr)
                logger.debug("USB address %x closed", addr)
            else:
                self.send_error("NOT_FOUND")

    return H2HInterfacesApi
