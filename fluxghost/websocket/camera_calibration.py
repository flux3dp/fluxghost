from fluxghost.api.camera_calibration import camera_calibration_api_mixin

from .base import WebSocketBase

"""

Javascript Example:

ws = new WebSocket("ws://127.0.0.1:8000/ws/camera_calibration");
ws.onmessage = function(v) { console.log(v.data);}
ws.onclose = function(v) { console.log("CONNECTION CLOSED, code=" + v.code +
    "; reason=" + v.reason); }

// After recive connected...
ws.send("ls")
"""


class WebsocketCameraCalibration(camera_calibration_api_mixin(WebSocketBase)):
    pass
