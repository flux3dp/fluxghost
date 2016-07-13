
import logging

from fluxclient.utils.version import StrictVersion
from .control_base import control_base_mixin

CRITICAL_VERSION = StrictVersion("1.3a1")
logger = logging.getLogger("API.CAMERA")


"""
Control printer

Javascript Example:

ws = new WebSocket("ws://localhost:8000/ws/control/RLFPAPI7E8KXG64KG5NOWWY3T");
ws.onmessage = function(v) { console.log(v.data);}
ws.onclose = function(v) { console.log("CONNECTION CLOSED, code=" + v.code +
    "; reason=" + v.reason); }

// After recive connected...
ws.send("ls")
"""


def camera_api_mixin(cls):
    class CameraAPI(control_base_mixin(cls)):
        _remote_version = None

        def get_robot_from_device(self, device):
            self._remote_version = device.version
            return device.connect_camera(
                self.client_key, conn_callback=self._conn_callback)

        def on_connected(self):
            if self._remote_version > CRITICAL_VERSION:
                logger.debug("Request streaming")
                self.robot.enable_streaming()
            self.rlist.append(CameraWrapper(self, self.robot))

        def on_image(self, camera, image):
            self.send_binary(image)
    return CameraAPI


class CameraWrapper(object):
    def __init__(self, ws, camera):
        self.ws = ws
        self.camera = camera
        # TODO: `camera.sock.fileno()` to `camera.fileno()`
        self._fileno = camera.sock.fileno()

    def fileno(self):
        return self._fileno

    def on_read(self):
        try:
            self.camera.feed(self.ws.on_image)
        except RuntimeError as e:
            logger.info("Camera error: %s", e)
            self.ws.close()
            self.camera = None
            self.ws = None
