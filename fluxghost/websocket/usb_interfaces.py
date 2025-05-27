from fluxghost.api.usb_interfaces import usb_interfaces_api_mixin

from .base import WebSocketBase


class WebsocketUsbInterfaces(usb_interfaces_api_mixin(WebSocketBase)):
    pass
