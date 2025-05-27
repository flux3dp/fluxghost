from fluxghost.api.inter_process import inter_process_api_mixin

from .base import WebSocketBase

"""

Javascript Example:

ws = new WebSocket("ws://127.0.0.1:8000/ws/inter_process");
ws.onmessage = function(v) { console.log(v.data);}
ws.onclose = function(v) { console.log("CONNECTION CLOSED, code=" + v.code +
    "; reason=" + v.reason); }

// After recive connected...
ws.send("ls")
"""


class WebsocketInterProcess(inter_process_api_mixin(WebSocketBase)):
    pass
