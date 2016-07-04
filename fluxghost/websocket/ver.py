

import logging
import json

import fluxclient
import fluxghost

from .base import WebSocketBase

logger = logging.getLogger("WS.VER")

"""
This websocket is use for get some basic information

Javascript Example:

ws = new WebSocket("ws://localhost:8000/ws/ver");
ws.onmessage = function(v) { console.log(v.data);}
ws.onclose = function(v) { console.log("CONNECTION CLOSED, code=" + v.code +
    "; reason=" + v.reason); }
"""


class WebsocketVer(WebSocketBase):
    def __init__(self, *args, **kw):
        super(WebsocketVer, self).__init__(*args, **kw)
        self.send_text(json.dumps({
            "fluxclient": fluxclient.__version__,
            "fluxghost": fluxghost.__version__
        }))
        self.close()
