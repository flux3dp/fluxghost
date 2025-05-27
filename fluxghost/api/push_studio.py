import logging

from .misc import BinaryHelperMixin, OnTextMessageMixin

logger = logging.getLogger(__file__)


def push_studio_api_mixin(cls):
    class PushStudioApi(OnTextMessageMixin, BinaryHelperMixin, cls):
        def __init__(self, *args, **kw):
            super().__init__(*args, **kw)
            self.cmd_mapping = {
                'set_handler': [self.cmd_set_handler],
            }
            self.server = args[2]

        def cmd_set_handler(self, message):
            self.server.set_push_studio_ws(self)
            logger.info('Set push studio ws')
            self.send_ok(cmd='set_handler')

    return PushStudioApi
