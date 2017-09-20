

from fluxghost.api.usb_config import usb_config_api_mixin
from .base import WebSocketBase

"""
This is a simple Usb websocket

Javascript Example:

ws = new WebSocket("ws://127.0.0.1:8000/ws/usb-config");
ws.onmessage = function(v) { console.log(v.data);}
ws.onclose = function(v) { console.log("CONNECTION CLOSED, code=" + v.code +
    "; reason=" + v.reason); }

ws.onopen = function() {
    ws.send("list")
    ws.send("connect /dev/ttyUSB0")
}
"""


class WebsocketUsbConfig(usb_config_api_mixin(WebSocketBase)):
    pass
