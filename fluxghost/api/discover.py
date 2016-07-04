
from time import time
import logging
import json

logger = logging.getLogger("API.DISCOVER")


def discover_api_mixin(cls):
    class DiscoverApi(cls):
        def __init__(self, *args):
            super().__init__(*args)
            self.alive_devices = set()
            self.server.discover_devices.items()
            self.POOL_TIME = 1.0

        def on_review_devices(self):
            t = time()

            with self.server.discover_mutex:
                for uuid, device in self.server.discover_devices.items():
                    if t - device.last_update > 30:
                        # Dead devices
                        if uuid in self.alive_devices:
                            self.alive_devices.remove(uuid)
                            self.send_text(self.build_dead_response(uuid))
                    else:
                        # Alive devices
                        self.alive_devices.add(uuid)
                        self.send_text(self.build_response(device))

        def on_text_message(self, message):
            try:
                payload = json.loads(message)
            except Exception as e:
                self.send_error("BAD_PARAMS", info=repr(e))
                return

            cmd = payload.get("cmd")
            if cmd == "poke":
                try:
                    self.server.discover.poke(payload["ipaddr"])
                except Exception as e:
                    logger.error("Poke error: %s", repr(e))
            else:
                self.send_error("UNKNOWN_COMMAND")

        def on_loop(self):
            self.on_review_devices()
            self.POOL_TIME = min(self.POOL_TIME + 1.0, 3.0)

        def on_closed(self):
            pass

        def build_dead_response(self, uuid):
            return json.dumps({
                "uuid": uuid.hex,
                "alive": False
            })

        def build_response(self, device):
            st = device.status
            payload = {
                "uuid": device.uuid.hex,
                "serial": device.serial,
                "version": str(device.version),
                "alive": True,
                "name": device.name,
                "ipaddr": device.ipaddr,

                "model": device.model_id,
                "password": device.has_password,
                "source": "lan",

                "st_ts": st.get("st_ts"),
                "st_id": st.get("st_id"),
                "st_prog": st.get("st_prog"),
                "head_module": st.get("head_module"),
                "error_label": st.get("error_label")
            }
            return json.dumps(payload)
    return DiscoverApi
