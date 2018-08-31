
from fluxghost.api.image_tracer import image_tracer_api_mixin
from .base import WebSocketBase


"""

Javascript Example:

ws = new WebSocket("ws://127.0.0.1:8000/ws/image_tracer");
ws.onmessage = function(v) { console.log(v.data);}
ws.onclose = function(v) { console.log("CONNECTION CLOSED, code=" + v.code +
    "; reason=" + v.reason); }

// After recive connected...
ws.send("ls")
"""


class WebsocketImageTracer(image_tracer_api_mixin(WebSocketBase)):
    pass
