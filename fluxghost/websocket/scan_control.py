
from fluxghost.api.scan_control import scan_control_api_mixin
from .base import WebSocketBase


"""
Control printer

Javascript Example:

ws = new WebSocket(
    "ws://localhost:8000/ws/3d-scan-control/RLFPAPI7E8KXG64KG5NOWWY3T");
ws.onmessage = function(v) { console.log(v.data);}
ws.onclose = function(v) { console.log("CONNECTION CLOSED, code=" + v.code +
    "; reason=" + v.reason); }

// After recive connected...
ws.send("image")
"""


class Websocket3DScanControl(scan_control_api_mixin(WebSocketBase)):
    pass
