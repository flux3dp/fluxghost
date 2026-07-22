"""Usage tests X1, X2, X3 (see docs/test-plan.md).

Covers the push-studio/inter-process message bus: the Beam Studio tab
registers itself on /ws/push-studio (`set_handler`, ai-extension.ts) and the
Adobe Illustrator plugin publishes SVG + layer settings on /ws/inter-process,
which relays them through the shared `server.push_studio_ws` slot.

Ordering matters: the handler slot is never cleared on disconnect
(docs/api/push-studio.md), so the only deterministic no-handler state on a
shared server is *before any test registers one*. unittest runs methods
alphabetically within a class, so the X3 method is named `test_a_...` to run
first, before X1/X2 ever call `set_handler`.
"""

import json
import socket
import unittest

from tests.usage._harness import WS, Server

server = None

SVG = b'<svg xmlns="http://www.w3.org/2000/svg"><rect width="10" height="10"/></svg>'
# Forwarded verbatim as a JSON *string*; must contain no spaces because the
# handler splits its params on spaces (fluxghost/api/inter_process.py).
LAYER_DATA = '{"Layer1":{"name":"Layer1","power":"50","speed":"30"}}'


def setUpModule():
    global server
    server = Server()


def tearDownModule():
    if server is not None:
        server.stop()


def drain_until_closed(ws, timeout=5):
    """Read frames until the server closes; return (closed, text_frames)."""
    ws.sock.settimeout(timeout)
    text_frames = []
    try:
        while True:
            op, payload = ws.frame()
            if op == 8:
                return True, text_frames
            if op == 1:
                text_frames.append(payload)
    except socket.timeout:
        return False, text_frames
    except (EOFError, ConnectionError, OSError):
        return True, text_frames


class PushChannelTest(unittest.TestCase):
    def test_a_x3_relay_without_handler_drops_connection(self):
        # pins current quirk, see docs/todo.md
        # X3: with no push-studio handler ever registered, server.push_studio_ws
        # is still None, so the relay callback raises AttributeError
        # (`None.send_ok`). Nothing catches it except the top-level
        # `except Exception` in WebSocketBase.serve_forever, which just closes
        # the raw socket: the publisher gets NO error frame, NO close frame —
        # only EOF after the binary upload completes.
        ws = WS(server.port, '/ws/inter-process')
        try:
            ws.send('connect')
            msg = json.loads(ws.frame()[1])
            self.assertEqual(msg, {'type': 'connect', 'status': 'ok'})

            ws.send('adobe_illustrator %d %s' % (len(SVG), LAYER_DATA))
            msg = json.loads(ws.frame()[1])
            self.assertEqual(msg, {'status': 'continue'})

            ws.send(SVG, opcode=2)
            closed, text_frames = drain_until_closed(ws)
            self.assertTrue(closed, 'connection stayed open after relay without handler')
            self.assertEqual(text_frames, [], 'expected a silent drop, got frames: %r' % text_frames)
        finally:
            ws.close()

    def test_b_x1_set_handler_replies_ok(self):
        # X1: `set_handler` (sent as a bare command, ai-extension.ts) registers
        # this socket as server.push_studio_ws and replies via
        # send_ok(cmd='set_handler') (fluxghost/api/push_studio.py).
        ws = WS(server.port, '/ws/push-studio')
        try:
            ws.send('set_handler')
            op, payload = ws.frame()
            self.assertEqual(op, 1)
            self.assertEqual(json.loads(payload), {'cmd': 'set_handler', 'status': 'ok'})
        finally:
            ws.close()

    def test_c_x2_adobe_illustrator_relays_to_push_studio(self):
        # X2: the inter-process publisher's upload lands on the registered
        # push-studio socket as {"svg", "layerData", "status": "ok"}; the
        # publisher itself gets nothing after {"status": "continue"}.
        studio = WS(server.port, '/ws/push-studio')
        plugin = None
        try:
            studio.send('set_handler')
            self.assertEqual(json.loads(studio.frame()[1]), {'cmd': 'set_handler', 'status': 'ok'})

            plugin = WS(server.port, '/ws/inter-process')
            plugin.send('connect')
            self.assertEqual(json.loads(plugin.frame()[1]), {'type': 'connect', 'status': 'ok'})

            plugin.send('adobe_illustrator %d %s' % (len(SVG), LAYER_DATA))
            self.assertEqual(json.loads(plugin.frame()[1]), {'status': 'continue'})
            plugin.send(SVG, opcode=2)

            # The pushed payload arrives on the *push-studio* socket.
            op, payload = studio.frame()
            self.assertEqual(op, 1)
            msg = json.loads(payload)
            self.assertEqual(msg['status'], 'ok')
            self.assertEqual(msg['svg'], SVG.decode('utf-8'))
            self.assertEqual(msg['layerData'], LAYER_DATA)  # verbatim JSON string, not an object
            self.assertEqual(json.loads(msg['layerData'])['Layer1']['power'], '50')
        finally:
            if plugin is not None:
                plugin.close()
            studio.close()


if __name__ == '__main__':
    unittest.main()
