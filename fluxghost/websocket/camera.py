
import logging

from .control import WebsocketControlBase

logger = logging.getLogger("WS.CAMERA")


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


STAGE_DISCOVER = '{"status": "connecting", "stage": "discover"}'
STAGE_ROBOT_CONNECTING = '{"status": "connecting", "stage": "connecting"}'
STAGE_CONNECTED = '{"status": "connected"}'
STAGE_TIMEOUT = '{"status": "error", "error": "TIMEOUT"}'


class WebsocketCamera(WebsocketControlBase):
    def get_robot_from_device(self, device):
        return device.connect_camera(
            self.client_key, conn_callback=self._conn_callback)

    def on_connected(self):
        self.rlist.append(CameraWrapper(self, self.robot))

    def on_image(self, camera, image):
        self.send_binary(image)


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
