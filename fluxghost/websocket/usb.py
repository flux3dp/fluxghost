

from fluxghost.api.usb import usb_interfaces_api_mixin, usb_control_api_mixin
from .base import WebSocketBase

"""
This is a simple Usb websocket

Javascript Example:

ws = new WebSocket("ws://localhost:8000/ws/usb");
ws.onmessage = function(v) { console.log(v.data);}
ws.onclose = function(v) { console.log("CONNECTION CLOSED, code=" + v.code +
    "; reason=" + v.reason); }

ws.onopen = function() {
    ws.send("list")
    ws.send("connect /dev/ttyUSB0")
}
"""


class UsbInterfaces(usb_interfaces_api_mixin(WebSocketBase)):
    pass


class USBControl(usb_control_api_mixin(WebSocketBase)):
    pass
