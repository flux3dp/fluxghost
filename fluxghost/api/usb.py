
from threading import Thread
import logging

from fluxclient.usb import usb2
from fluxghost.api.control import control_api_mixin
from fluxghost import g

logger = logging.getLogger("API.USB")


def usb_daemon_thread(protocol, address):
    logger.debug("USB daemon at %s start", address)
    g.USBDEVS[address] = protocol
    try:
        protocol.run()
        g.USBDEVS.pop(address)
        logger.debug("USB daemon at %s terminated", address)
    except Exception:
        logger.exception("USB daemon at %s crashed", address)
    g.USBDEVS.pop(address)
    protocol.close()


def usb_interfaces_api_mixin(cls):
    class USBInterfacesApi(cls):
        def __init__(self, *args, **kw):
            super().__init__(*args, **kw)
            self.cached = set()

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

        def update_devices(self):
            usbdevs = {}
            ifces = usb2.USBProtocol.get_interfaces()
            for i in ifces:
                if i.address in g.USBDEVS:
                    usbdevs[i.address] = g.USBDEVS[i.address]
                else:
                    usbdevs[i.address] = None
            g.USBDEVS = usbdevs

        def list_devices(self):
            self.update_devices()
            output = {}
            for k, v in g.USBDEVS.items():
                if v:
                    if k in self.cached:
                        output[k] = True
                    else:
                        self.cached.add(k)
                        output[k] = v.endpoint_profile
                else:
                    self.cached.discard(k)
                    output[k] = False

            self.send_ok(devices=output)

        def open_device(self, addr):
            if g.USBDEVS.get(addr):
                self.send_error("RESOURCE_BUSY")
                return

            for usbdev in usb2.USBProtocol.get_interfaces():
                if usbdev.address == addr:
                    try:
                        usbprotocol = usb2.USBProtocol(usbdev)
                        t = Thread(target=usb_daemon_thread,
                                   args=(usbprotocol, addr))
                        t.daemon = True
                        t.start()
                        self.send_ok(devopen=addr,
                                     profile=usbprotocol.endpoint_profile)
                        logger.debug("USB address %s opened: %s", addr,
                                     usbprotocol.endpoint_profile)
                        return
                    except usb2.FluxUSBError as e:
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
    return USBInterfacesApi


def usb_control_api_mixin(cls):
    class USBControlApi(control_api_mixin(cls)):
        def __init__(self, *args, **kw):
            super().__init__(*args, **kw)
    return USBControlApi
