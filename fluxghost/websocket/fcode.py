import json
from tempfile import NamedTemporaryFile

from .base import WebSocketBase


class WebsocketFcode(WebSocketBase):
    stream = None

    def on_binary_message(self, buf):
        if self.binary_handler:
            self.binary_handler(buf)
        else:
            self.send_fatal('PROTOCOL_ERROR', 'Can not accept binary data')

    def begin_binary_transfer(self, size):
        def binary_handler(buf):
            self.stream.write(buf)
            sent = self.stream.tell()
            self.send_json(status='uploading', sent=sent)
            if sent >= size:
                self.stream.seek(0)
                self.convert()
                self.close()

        with NamedTemporaryFile() as temp_stream:
            self.stream = temp_stream
            self.binary_handler = binary_handler
            self.send_continue()

    def on_text_message(self, message):
        if self.stream:
            self.send_fatal('PROTOCOL_ERROR', 'Can not accept text data')

        try:
            req = json.loads(message)
            self.request = {'action': req['action'], 'metadata': req['metadata'], 'head_type': req['head_type']}
            self.request = json.loads(message)
            self.begin_binary_transfer(self.request['size'])
        except Exception as e:
            self.send_json(status='error', log=str(e))
            self.close()

    def convert(self):
        action = self.request['action']
        if action == 'g2f':
            self.send_json(status=action)
            from fluxclient.fcode.g_to_f import GcodeToFcode

            conv = GcodeToFcode(head_type=self.request['head_type'], ext_metadata=self.request['metadata'])

            with NamedTemporaryFile() as output:
                conv.process(self.stream, output)

        else:
            self.send_json(status='error', log='Unknown action: %s' % action)

    def feedback(self, stream, mimetype, size):
        self.send_json(status='binary', mimetype=mimetype, size=size)

        left = size
        while left > 0:
            buf = stream.read(min(4096, left))
            self.send_binary(buf)
            left -= len(buf)

        self.send_ok()
