
from fluxghost.api.upnp import upnp_api_mixin
from .base import WebSocketBase


class WebsocketUpnp(upnp_api_mixin(WebSocketBase)):
    pass
