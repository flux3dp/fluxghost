
from time import time
from uuid import UUID
import logging
import json

from .base import WebSocketBase, SIMULATE

logger = logging.getLogger("WS.DISCOVER")

"""
Find devices on local network, cloud and USB

Javascript Example:

ws = new WebSocket("ws://localhost:8000/ws/discover");
ws.onmessage = function(v) { console.log(v.data);}
ws.onclose = function(v) { console.log("CONNECTION CLOSED, code=" + v.code +
    "; reason=" + v.reason); }
"""


class WebsocketDiscover(WebSocketBase):
    def __init__(self, *args):
        WebSocketBase.__init__(self, *args)

        if SIMULATE:
            u = UUID(hex="0" * 32)
            self.send_text(
                self.build_response(
                    uuid=u, serial="SIMULATE00", model_id="magic",
                    timestemp=0, name="Simulate Device", version="god knows",
                    has_password=False, ipaddr="1.1.1.1"))

        self.alive_devices = []
        self.POOL_TIME = 1.0

    def on_review_devices(self):
        t = time()

        for uuid, data in self.server.discover_devices.items():
            if t - data.get("last_response", 0) > 30:
                # Dead devices
                if uuid in self.alive_devices:
                    self.alive_devices.pop()
                    self.send_text(self.build_dead_response(uuid))
            else:
                # Alive devices
                if uuid not in self.alive_devices:
                    self.alive_devices.append(uuid)
                    self.send_text(self.build_response(uuid, **data))

    def on_loop(self):
        self.on_review_devices()
        self.POOL_TIME = min(self.POOL_TIME + 1.0, 3.0)

    def build_dead_response(self, uuid):
        # TODO: serial -- uuid.hex to real serial
        return json.dumps({
            "uuid": uuid.hex,
            "serial": uuid.hex,
            "alive": False
        })

    def build_response(self, uuid, serial, model_id, name, version,
                       has_password, ipaddr, **kw):
        # TODO: serial -- uuid.hex to real serial
        payload = {
            "uuid": uuid.hex,
            "serial": serial,
            "version": version,
            "alive": True,
            "name": name,
            "ipaddr": ipaddr[0],

            "model": model_id,
            "password": has_password,
            "source": "lan"
        }
        return json.dumps(payload)
