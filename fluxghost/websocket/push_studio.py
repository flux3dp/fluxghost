
from fluxghost.api.push_studio import push_studio_api_mixin
from .base import WebSocketBase


"""

Javascript Example:

ws = new WebSocket("ws://127.0.0.1:8000/ws/push_studio");
ws.onmessage = function(v) { console.log(v.data);}
ws.onclose = function(v) { console.log("CONNECTION CLOSED, code=" + v.code +
    "; reason=" + v.reason); }

// After recive connected...
ws.send("ls")
"""


class WebsocketPushStudio(push_studio_api_mixin(WebSocketBase)):
    pass
