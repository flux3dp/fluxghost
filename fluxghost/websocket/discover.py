
from fluxghost.api.discover import discover_api_mixin
from .base import WebSocketBase

"""
Find devices on local network, cloud and USB

Javascript Example:

ws = new WebSocket("ws://localhost:8000/ws/discover");
ws.onmessage = function(v) { console.log(v.data);}
ws.onclose = function(v) { console.log("CONNECTION CLOSED, code=" + v.code +
    "; reason=" + v.reason); }
"""


class WebsocketDiscover(discover_api_mixin(WebSocketBase)):
    pass
