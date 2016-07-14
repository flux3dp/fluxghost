
from fluxghost.api.touch import touch_api_mixin
from .base import WebSocketBase


class WebsocketTouch(touch_api_mixin(WebSocketBase)):
    pass
