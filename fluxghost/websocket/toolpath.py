import logging

from fluxghost.api.svgeditor_toolpath import laser_svgeditor_api_mixin

from .base import WebSocketBase

logger = logging.getLogger('websocket.toolpath')

logger.info('Importing svgeditor_toolpath')


class WebsocketLaserSvgeditor(laser_svgeditor_api_mixin(WebSocketBase)):
    pass
