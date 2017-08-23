
from time import time
import logging
import json

from fluxghost import g

logger = logging.getLogger("API.DISCOVER")


def get_online_message(source, device):
    st = None
    doc = {
        "uuid": device.uuid.hex,
        "alive": True,
        "source": source,
        "serial": device.serial,
        "version": str(device.version),
        "model": device.model_id,
    }

    if source == "lan":
        doc.update({
            "name": device.name,
            "ipaddr": device.ipaddr,
            "password": device.has_password,
        })
        st = device.status
    elif source == "h2h":
        st = device.device_status
        doc.update({
            "name": device.nickname,
            "addr": device.addr,
        })
    else:
        st = {}

    doc.update({
        "st_ts": st.get("st_ts"),
        "st_id": st.get("st_id"),
        "st_prog": st.get("st_prog"),
        "head_module": st.get("st_head", st.get("head_module")),
        "error_label": st.get("st_err", st.get("error_label"))
    })
    return doc


def get_offline_message(source, device=None, uuid=None):
    return {
        "uuid": device.uuid.hex if device else uuid.hex,
        "alive": False,
        "source": source
    }


def discover_api_mixin(cls):
    class DiscoverApi(cls):
        def __init__(self, *args):
            super().__init__(*args)
            self.lan_alive_devices = set()
            self.usb_alive_addr = {}
            self.server.discover_devices.items()
            self.POOL_TIME = 1.0

        def review_lan_devices(self):
            t = time()

            with self.server.discover_mutex:
                for uuid, device in self.server.discover_devices.items():
                    if t - device.last_update > 30:
                        # Dead devices
                        if uuid in self.lan_alive_devices:
                            self.lan_alive_devices.remove(uuid)
                            self.send_text(self.build_dead_response("lan",
                                                                    device))
                    else:
                        # Alive devices
                        self.lan_alive_devices.add(uuid)
                        self.send_text(self.build_response("lan", device))

        def review_usb_devices(self):
            rmlist = []
            for addr, uuid in self.usb_alive_addr.items():
                usbprotocol = g.USBDEVS.get(addr)
                if usbprotocol and usbprotocol.uuid == uuid:
                    pass
                else:
                    rmlist.append(addr)
                    self.send_text(self.build_dead_response("h2h", uuid=uuid))
            for addr in rmlist:
                self.usb_alive_addr.pop(addr)

            for addr, usbdevice in g.USBDEVS.items():
                if addr not in self.usb_alive_addr:
                    self.usb_alive_addr[addr] = usbdevice.uuid
                self.send_text(self.build_response("h2h", usbdevice))

        def on_review_devices(self):
            self.review_lan_devices()
            self.review_usb_devices()

        def on_text_message(self, message):
            try:
                payload = json.loads(message)
            except Exception as e:
                self.traceback("BAD_PARAMS")
                return

            cmd = payload.get("cmd")
            if cmd == "poke":
                try:
                    self.server.discover.poke(payload["ipaddr"])
                except Exception as e:
                    logger.error("Poke error: %s", repr(e))
            else:
                self.send_error("L_UNKNOWN_COMMAND")

        def on_loop(self):
            self.on_review_devices()
            self.POOL_TIME = min(self.POOL_TIME + 1.0, 3.0)

        def on_closed(self):
            pass

        def build_dead_response(self, source, device=None, uuid=None):
            return json.dumps(
                get_offline_message(source, device=device, uuid=uuid))

        def build_response(self, source, device):
            return json.dumps(get_online_message(source, device))

    return DiscoverApi
