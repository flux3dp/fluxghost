
from time import time
from uuid import UUID
from fluxclient.utils.version import StrictVersion
from .camera import SimulateCamera
from .robot import SimulateRobot


class SimulatePlayerMixIn(object):
    __simulate_player = None

    def simulate_player(self, timecost=60, ):
        from threading import Thread

        def player():
            pass

    def simulate_report_play(self):
        return {"st_id": 0, "st_label": "IDLE"}


class SimulateDevice(SimulatePlayerMixIn):
    uuid = UUID(int=0)
    serial = "XXXXXXXXXX"
    version = StrictVersion("1.1.4")
    name = "Simulate Device"
    ipaddr = "127.0.0.1"
    model_id = "simulate"
    has_password = True

    # Dynamic contents:
    st_id = 0
    st_label = "ST_IDLE"
    st_prog = 0
    head_module = "n/a"
    error_label = ""

    @property
    def last_update(self):
        return time()

    @property
    def status(self):
        return {
            "st_id": self.st_id,
            "st_label": self.st_label,
            "st_prog": self.st_prog,
            "head_module": self.head_module,
            "error_label": self.error_label,
            "last_update": self.last_update
        }

    def connect_robot(self, clientkey, **kw):
        return SimulateRobot(self)

    def connect_camera(self, clientkey, **kw):
        return SimulateCamera()
