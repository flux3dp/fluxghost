
from fluxghost.api.usb_config import usb_config_api_mixin
from .base import PipeBase


class PipeUsbConfig(usb_config_api_mixin(PipeBase)):
    pass
