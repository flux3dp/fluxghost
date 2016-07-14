
from fluxghost.api.ver import ver_api_mixin
from .base import WebSocketBase

"""
This websocket is use for get some basic information

Javascript Example:

ws = new WebSocket("ws://localhost:8000/ws/ver");
ws.onmessage = function(v) { console.log(v.data);}
ws.onclose = function(v) { console.log("CONNECTION CLOSED, code=" + v.code +
    "; reason=" + v.reason); }
"""


class WebsocketVer(ver_api_mixin(WebSocketBase)):
    pass
