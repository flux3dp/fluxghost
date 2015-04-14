
from hashlib import sha1
import logging
import base64

from fluxghost.utils.websocket import MAGIC_STRING

logger = logging.getLogger("WebSocketHandler")


class WebSocketHandler(object):
    """WebSocketHandler handle websocket handshake. After handshake, handler
    will move to ws_class"""

    def handle_request(self, handler):
        handler.close_connection = 1
        upgrade = handler.headers.get('Upgrade')
        conn = handler.headers.get('Connection')
        ws_version = handler.headers.get('Sec-WebSocket-Version')
        ws_key = handler.headers.get('Sec-WebSocket-Key')

        if not (upgrade and (upgrade.lower() == 'websocket')):
            logger.error("Bad Header 'Upgrade': %s" % upgrade)
            handler.response_403(body="Bad WebSocket request")
            return False

        if not (conn and ('upgrade' in conn.lower().split(', '))):
            logger.error("Bad Header 'Connection': %s" % conn)
            handler.response_403(body="Bad WebSocket request")
            return False

        if not (ws_version and (13 in map(int, ws_version.split(',')))):
            logger.error("Bad Header 'Sec-WebSocket-Version': %s" % ws_version)
            handler.response_403(body="Bad WebSocket request")
            return False

        self.handshake(handler, ws_key)
        return True

    def handshake(self, handler, ws_key, **kw):
        handshake_key = ('%s%s' % (ws_key, MAGIC_STRING)).encode()
        accept_key = base64.encodestring(sha1(handshake_key).digest())[:-1]

        handler.send_response(101, 'Switching Protocols')
        handler.send_header('Upgrade', 'websocket')
        handler.send_header('Connection', 'Upgrade')
        handler.send_header('Sec-WebSocket-Accept', accept_key.decode('ascii'))
        handler.end_headers()
