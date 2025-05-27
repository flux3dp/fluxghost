from fluxghost.api.device_manager import manager_mixin

from .base import WebSocketBase


class WebsocketDeviceManager(manager_mixin(WebSocketBase)):
    pass
