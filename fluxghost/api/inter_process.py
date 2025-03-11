import logging

from .misc import BinaryUploadHelper, BinaryHelperMixin, OnTextMessageMixin

logger = logging.getLogger("API.INTER_PROCESS")

def inter_process_api_mixin(cls):
    class InterProcessApi(OnTextMessageMixin, BinaryHelperMixin, cls):
        def __init__(self, *args, **kw):
            super(InterProcessApi, self).__init__(*args, **kw)
            self.http_handler = args[2]
            self.cmd_mapping = {
                'connect': [self.cmd_connect],
                'adobe_illustrator': [self.cmd_adobe_illustrator],
            }

        def cmd_connect(self, message):
            self.send_ok(type = 'connect')

        def cmd_adobe_illustrator(self, message):
            message = message.split(" ")
            def inter_process_callback(buf):
                svg = str(buf, encoding = "utf-8")
                self.http_handler.push_studio_ws.send_ok(svg = svg, layerData = message[1])

            file_length = message[0]
            helper = BinaryUploadHelper(int(file_length), inter_process_callback)
            self.set_binary_helper(helper)
            self.send_json(status="continue")

    return InterProcessApi
