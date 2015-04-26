
from time import time
import logging
import socket
import struct
import json

from .base import WebSocketBase

logger = logging.getLogger("WS.DISCOVER")

CODE_DISCOVER = 0x00
CODE_RESPONSE_DISCOVER = 0x01

"""
Find devices on local network, cloud and USB

Javascript Example:

ws = new WebSocket("ws://localhost:8080/ws/discover");
ws.onmessage = function(v) { console.log(v.data);}
ws.onclose = function(v) { console.log("CONNECTION CLOSED, code=" + v.code +
    "; reason=" + v.reason); }
"""


class WebsocketDiscover(WebSocketBase):
    @classmethod
    def match_route(klass, path):
        return path == "discover"

    def __init__(self, *args, **kw):
        WebSocketBase.__init__(self, *args, **kw)

        self.upnp_discover_socket = UpnpDiscoverSocket(self)
        self.upnp_discover_socket.poke()
        self.devices = {}

        self.rlist.append(self.upnp_discover_socket)
        self.POOL_TIME = 0.3

    def onMessage(self, message, is_binary):
        self.POOL_TIME = 0.3

    def on_recv_discover(self, payload, discover_from):
        serial = payload.get("serial")

        if serial in self.devices:
            profile = self.devices[serial]
        else:
            self.devices[serial] = profile = {
                "serial": serial,
                "from_lan": False, "from_cloud": False, "from_usb": False,
                "last_lan_update": 0
            }

        changed = self.update_profile(payload, profile, discover_from)

        if changed:
            self.send_text(self.build_response(profile))

    def on_review_devices(self):
        t = time()
        for serial, profile in self.devices.items():
            has_gone = False

            if profile["from_lan"]:
                if t - profile["last_lan_update"] > 15.0:
                    profile["from_lan"] = False
                    has_gone = True

            if has_gone:
                self.send_text(self.build_response(profile))

    def on_loop(self):
        self.on_review_devices()

        self.POOL_TIME = min(self.POOL_TIME + 1.0, 3.0)
        self.upnp_discover_socket.poke()

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

    def build_response(self, profile):
        payload = {
            "serial": profile.get("serial"),
            "name": "My FLUX Printer",
            "model": profile.get("model"),
            "password": profile.get("pwd"),
            "from_lan": profile["from_lan"],
            "from_cloud": profile["from_cloud"],
            "from_usb": profile["from_usb"]
        }
        return json.dumps(payload)

class UpnpDiscoverSocket(object):
    def __init__(self, ws, ipaddr="255.255.255.255", port=3310):
        self.ws = ws
        self.dist = (ipaddr, port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM,
                                  socket.IPPROTO_UDP)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self._fileno = self.sock.fileno()

        self.discover_payload = struct.pack('<4s16sh', b"FLUX",
                                            b"\x00" * 16, CODE_DISCOVER)
        self.last_poke = 0

    def on_read(self):
        buf, remote = self.sock.recvfrom(4096)

        try:
            payload = json.loads(buf[:-1].decode("utf8"))
            code = payload.pop("code")

            if code == CODE_RESPONSE_DISCOVER:
                payload["from_lan"] = True
                self.ws.on_recv_discover(payload, "lan")
                
        except Exception as e:
            logger.debug("Unpack message error: %s" % e)

    def poke(self):
        t = time()
        if t - self.last_poke > 0.3:
            self.sock.sendto(self.discover_payload, self.dist)
            self.last_poke = t

    def fileno(self):
        return self._fileno
