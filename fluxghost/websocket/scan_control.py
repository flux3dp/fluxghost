
from fluxghost.api.scan_control import scan_control_api_mixin
from fluxghost.api.scan_control_sim import scan_control_api_mixin_sim
from .base import WebSocketBase


"""
Control printer

Javascript Example:

ws = new WebSocket(
    "ws://127.0.0.1:8000/ws/3d-scan-control/RLFPAPI7E8KXG64KG5NOWWY3T");
ws.onmessage = function(v) { console.log(v.data);}
ws.onclose = function(v) { console.log("CONNECTION CLOSED, code=" + v.code +
    "; reason=" + v.reason); }

// After recive connected...
ws.send("image")
"""


class Websocket3DScanControl(scan_control_api_mixin(WebSocketBase)):
    pass


class Websocket3DScanControlSimulation(scan_control_api_mixin_sim(WebSocketBase)):
    pass
