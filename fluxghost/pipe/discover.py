
from select import select
from time import time

from fluxclient.upnp import UpnpDiscover
from fluxghost.api.discover import get_online_message, get_offline_message
from .base import PipeBase


class DevicesMonitor(object):
    def __init__(self, offline_timeout=15):
        self.offline_timeout = offline_timeout
        self.all_devices = {}
        self.alive_devices = set()

    def online_device(self, device):
        self.all_devices[device.uuid] = device
        self.alive_devices.add(device.uuid)
        return get_online_message(device)

    def offline_devices(self):
        t = time()
        for uuid, device in self.all_devices.items():
            if t - device.last_update > self.offline_timeout:
                if uuid in self.alive_devices:
                    self.alive_devices.remove(uuid)

                    yield get_offline_message(device)


class PipeDiscover(PipeBase):
    def __init__(self, *args):
        super().__init__(*args)
        self.devices_monitor = DevicesMonitor()
        self.discover = UpnpDiscover()

    def _serve_forever(self):
        while self.running:
            rlist = list(self.rlist) + list(self.discover.socks)
            args = (rlist, (), (), 5.)
            rl = select(*args)[0]

            for r in rl:
                if r in self.discover.socks:
                    self.discover.try_recive(
                        self.discover.socks, callback=self.on_discover_device,
                        timeout=0.01)
                else:
                    r.on_read()

            self._on_loop()
            self.on_loop()

    def on_discover_device(self, discover_instance, uuid, device, **kw):
        self.send_json(self.devices_monitor.online_device(device))

    def on_loop(self):
        for message in self.devices_monitor.offline_devices():
            self.send_json(message)
