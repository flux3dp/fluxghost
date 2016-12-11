

from fluxghost.api.host2host_usb import (h2h_interfaces_api_mixin)
from .base import WebSocketBase


class H2HInterfaces(h2h_interfaces_api_mixin(WebSocketBase)):
    pass
