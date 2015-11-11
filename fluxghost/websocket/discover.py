
from time import time
import logging
import json

from fluxclient.upnp.discover import UpnpDiscover
from fluxclient.upnp.misc import uuid_to_short
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


class AsyncCallback(object):
    def __init__(self, f, d, callback):
        self.f = f
        self.d = d
        self.cb = callback

    def fileno(self):
        return self.f.fileno()

    def on_read(self, *args):
        self.d.try_recive((self.f, ), self.cb)


# class AsyncUpnpDiscover(UpnpDiscover):
#     def __init__(self, callback):
#         super(AsyncUpnpDiscover, self).__init__()
#         self.callback = callback
#
#     def fileno(self):
#
#
#     def on_read(self):
#         data = self.on_recv_pong()
#         self.callback(**data)


def create_async_discover(callback):
    discov = UpnpDiscover()
    f1 = AsyncCallback(discov.disc_sock, discov, callback)
    f2 = AsyncCallback(discov.touch_sock, discov, callback)
    return discov, f1, f2


class WebsocketDiscover(WebSocketBase):
    def __init__(self, *args):
        WebSocketBase.__init__(self, *args)

        self.discover, self.f1, self.f2 = create_async_discover(
            self.on_recv_discover
        )

        # self.discover = AsyncUpnpDiscover(callback=self.on_recv_discover)
        self.devices = {}

        self.rlist.append(self.f1)
        self.rlist.append(self.f2)

        if SIMULATE:
            self.send_text(
                self.build_response(
                    serial="0" * 32, model_id="magic", timestemp=0,
                    name="Simulate Device", version="god knows",
                    has_password=False, ipaddrs="1.1.1.1"))

        self.POOL_TIME = 0.3

    def on_text_message(self, message):
        self.POOL_TIME = 0.3

    def on_recv_discover(self, instance, **data):
        serial = data.get("serial")
        if serial not in self.devices:
            self.send_text(self.build_response(**data))

        self.devices[serial] = time()

    def on_review_devices(self):
        t = time()
        dead = []
        for serial, last_response in self.devices.items():
            if t - last_response > 45.:
                dead.append(serial)
                self.send_text(self.build_dead_response(serial))

        for serial in dead:
            self.devices.pop(serial)

    def on_loop(self):
        self.on_review_devices()
        self.POOL_TIME = min(self.POOL_TIME + 1.0, 3.0)

    def update_profile(self, source, target, discover_from):
        changed = False

        self.update_field(source, target, "time")
        for key in ["ver", "model", "ip", "pwd", "from_%s" % discover_from]:
            field_changed = self.update_field(source, target, key)
            if field_changed:
                changed = True

        target["last_%s_update" % discover_from] = time()
        return changed

    def update_field(self, source, target, key):
        new_val = source.get(key)
        old_val = target.get(key)
        if new_val == old_val:
            return False
        else:
            target[key] = new_val
            return True

    def build_dead_response(self, serial):
        return json.dumps({
            "serial": uuid_to_short(serial),
            "alive": False
        })

    def build_response(self, uuid, serial, model_id, name, timestemp, version,
                       has_password, **kw):
        payload = {
            "uuid": uuid.hex,
            "serial": uuid.hex,
            "version": version,
            "alive": True,
            "name": name,

            "model": model_id,
            "password": has_password,
            "source": "lan"
        }
        return json.dumps(payload)
