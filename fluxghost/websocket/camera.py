
from errno import EHOSTDOWN, errorcode
import logging

from fluxclient.robot import connect_camera
from fluxclient.robot.errors import RobotError
from fluxclient.encryptor import KeyObject
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
    def on_text_message(self, message):
        if self.client_key:
            self.on_command(message)
        else:
            self.client_key = client_key = KeyObject.load_keyobj(message)
            self.send_text(STAGE_DISCOVER)
            logger.debug("DISCOVER")

            try:
                task = self._discover(self.uuid, client_key)
                self.send_text(STAGE_ROBOT_CONNECTING)
                self.robot = connect_camera(
                    (self.ipaddr, 23812),
                    server_key=task.device_meta["master_key"],
                    metadata=task.device_meta,
                    client_key=client_key, conn_callback=self._conn_callback)
            except OSError as err:
                error_no = err.args[0]
                if error_no == EHOSTDOWN:
                    self.send_fatal("DISCONNECTED")
                else:
                    self.send_fatal("UNKNOWN_ERROR",
                                    errorcode.get(error_no, error_no))
                raise
            except RobotError as err:
                self.send_fatal(err.args[0], )
                raise

            self.remote_version = task.version
            self.send_text(STAGE_CONNECTED)
            self.on_connected()
            self.rlist.append(CameraWrapper(self, self.robot))

    def on_image(self, camera, image):
        self.send_binary(image)


class CameraWrapper(object):
    def __init__(self, ws, camera):
        self.ws = ws
        self.camera = camera
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
