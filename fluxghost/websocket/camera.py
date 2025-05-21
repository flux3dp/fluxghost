from fluxghost.api.camera import camera_api_mixin

from .base import WebSocketBase

"""
Control printer

Javascript Example:

ws = new WebSocket("ws://127.0.0.1:8000/ws/control/RLFPAPI7E8KXG64KG5NOWWY3T");
ws.onmessage = function(v) { console.log(v.data);}
ws.onclose = function(v) { console.log("CONNECTION CLOSED, code=" + v.code +
    "; reason=" + v.reason); }

// After recive connected...
ws.send("ls")
"""


class WebsocketCamera(camera_api_mixin(WebSocketBase)):
    pass
