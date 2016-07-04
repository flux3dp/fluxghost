
from fluxghost.api.upnp import upnp_api_mixin
from .base import MixedWebsocketBase


class WebsocketUpnp(upnp_api_mixin(MixedWebsocketBase)):
    pass
