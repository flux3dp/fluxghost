
"""
Commands

`list`
function: list available usb interfaces
return:
    {
        "h2h":{<DEVICE_ADDR>: <DEVICE_STATUS>, <DEVICE_ADDR>: <DEVICE_STATUS>...,
        "uart": [<UART_PORT>, ...]
    }
    <DEVICE_ADDR>: USB Address
    <DEVICE_STATUS>: USB hardware status. If the usb address is opened, it will
        return a object contains device basic informations otherwise it will
        return false.
    <UART_PORT>: Available uart interfaces
errors: n/a

`open <DEVICE_ADDR>`
function: open h2h usb device
return:
    {
        "devopen": <DEVICE_ADDR>,
        "profile": <DEVICE_STATUS>
    }
errors:
    TIMEOUT: device no response
    UNAVAILABLE: device could not be used. Maybe occupied by other program.
    UNKNOWN_ERROR: unhandle error during opening/io usb device.
"""

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

            self.send_ok(h2h=h2h, uart=uart, cmd="list")

        def open_device(self, addr):
            if g.USBDEVS.get(addr):
                self.send_error("RESOURCE_BUSY", cmd="open")
                return

            for usbdev in USBProtocol.get_interfaces():
                if usbdev.address == addr:
                    try:
                        usbprotocol = USBProtocol.connect(usbdev)
                        t = Thread(target=h2h_usb_daemon_thread,
                                   args=(usbprotocol, addr))
                        t.daemon = True
                        t.name = "USB Daemon: %s" % addr
                        t.start()
                        self.send_ok(devopen=addr,
                                     profile=usbprotocol.endpoint_profile,
                                     cmd="open")
                        logger.debug("USB address %s opened: %s", addr,
                                     usbprotocol.endpoint_profile)
                        return
                    except FluxUSBError as e:
                        self.send_error(e.symbol, cmd="open")
                        return
            self.send_error("NOT_FOUND", cmd="open")

        def close_device(self, addr):
            usbprotocol = g.USBDEVS.get(addr)
            if usbprotocol:
                usbprotocol.stop()
                self.send_ok(devclose=addr, cmd="close")
                logger.debug("USB address %x closed", addr)
            else:
                self.send_error("NOT_FOUND", cmd="close")

    return H2HInterfacesApi
