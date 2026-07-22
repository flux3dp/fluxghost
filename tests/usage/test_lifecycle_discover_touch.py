"""Usage tests L1, L2, D1, D2, D3, T1, T2 (see docs/test-plan.md).

Covers server lifecycle (`--port 0` ready line, /ws/ver), the discover
endpoint as Beam Studio's discover.ts drives it, and the touch endpoint as
touch.ts drives it. One shared server per module.
"""

import json
import unittest

from tests.usage._harness import SIM_UUID, WS, Server, make_rsa_pem

server = None


def setUpModule():
    global server
    server = Server()


def tearDownModule():
    if server is not None:
        server.stop()


class LifecycleTest(unittest.TestCase):
    def test_l1_ready_line_reports_port(self):
        # L1: `--port 0` printed {"type": "ready", "port": N} on stdout —
        # Server._wait_ready already parsed it; make the contract explicit.
        self.assertIsInstance(server.port, int)
        self.assertGreater(server.port, 0)

    def test_l2_ver_pushes_versions_then_closes(self):
        # L2: /ws/ver pushes {fluxghost, fluxclient} on connect, then closes.
        ws = WS(server.port, '/ws/ver')
        try:
            op, payload = ws.frame()
            self.assertEqual(op, 1)
            msg = json.loads(payload)
            self.assertIn('fluxghost', msg)
            self.assertIn('fluxclient', msg)
            self.assertTrue(msg['fluxghost'])
            self.assertTrue(msg['fluxclient'])
            self.assertNotIn('status', msg)  # ver has no status field (docs/api/ver.md)
            self.assertTrue(ws.expect_closed())
        finally:
            ws.close()


class DiscoverTest(unittest.TestCase):
    def test_d1_announcement_carries_all_frontend_fields(self):
        # D1: every field Beam Studio's discover.ts reads must be present.
        ws = WS(server.port, '/ws/discover')
        try:
            msg = ws.json_until(lambda m: m.get('uuid') == SIM_UUID and m.get('alive'))
            for field in (
                'uuid',
                'serial',
                'version',
                'model',
                'name',
                'ipaddr',
                'password',
                'alive',
                'source',
                'st_id',
                'st_prog',
                'head_module',
                'error_label',
            ):
                self.assertIn(field, msg, 'discover announcement missing %r' % field)
            self.assertIn('st_ts', msg)  # present but may be null
            self.assertEqual(msg['uuid'], SIM_UUID)
            self.assertIs(msg['alive'], True)
            self.assertEqual(msg['source'], 'lan')
            self.assertEqual(msg['ipaddr'], '127.0.0.1')
            self.assertEqual(msg['model'], 'simulate')
        finally:
            ws.close()

    def test_d2_poke_localhost_is_accepted(self):
        # D2: {"cmd": "poke", "ipaddr": "127.0.0.1"} produces no direct reply
        # and no error; device pushes keep flowing on the same connection.
        ws = WS(server.port, '/ws/discover')
        try:
            ws.send(json.dumps({'cmd': 'poke', 'ipaddr': '127.0.0.1'}))
            seen_alive = False
            for _ in range(3):
                op, payload = ws.frame()
                if op != 1:
                    continue
                self.assertNotEqual(payload, b'BAD_PARAMS')
                msg = json.loads(payload)
                self.assertNotEqual(msg.get('status'), 'error', 'poke replied with an error: %r' % (msg,))
                if msg.get('uuid') == SIM_UUID and msg.get('alive'):
                    seen_alive = True
            self.assertTrue(seen_alive, 'device pushes stopped after poke')
        finally:
            ws.close()

    def test_d3_malformed_poke_gets_plain_text_bad_params(self):
        # pins current quirk, see docs/todo.md
        # D3: unparseable JSON gets the plain-text frame "BAD_PARAMS" (not
        # JSON, no status field) and the connection stays open
        # (fluxghost/api/discover.py on_text_message).
        ws = WS(server.port, '/ws/discover')
        try:
            ws.send('this is not json {')
            for _ in range(10):
                op, payload = ws.frame()
                if op == 1 and payload == b'BAD_PARAMS':
                    break
            else:
                self.fail('BAD_PARAMS reply not received')
            # Connection is still usable: device pushes continue.
            msg = ws.json_until(lambda m: m.get('uuid') == SIM_UUID and m.get('alive'))
            self.assertEqual(msg['source'], 'lan')
        finally:
            ws.close()


class TouchTest(unittest.TestCase):
    @unittest.skipIf(make_rsa_pem() is None, 'pycryptodome not installed; cannot build an RSA key')
    def test_t1_simulate_touch_succeeds(self):
        # T1: touching the all-zero uuid replies with the simulate-device
        # success payload (fluxghost/api/touch.py touch_device).
        pem = make_rsa_pem()
        ws = WS(server.port, '/ws/touch')
        try:
            ws.send(json.dumps({'key': pem, 'uuid': SIM_UUID, 'password': ''}))
            op, payload = ws.frame()
            self.assertEqual(op, 1)
            msg = json.loads(payload)
            self.assertEqual(msg['serial'], 'SIMULATE00')
            self.assertEqual(msg['name'], 'Simulate Device')
            self.assertIs(msg['auth'], True)
            self.assertIs(msg['has_response'], True)
            self.assertIs(msg['reachable'], True)
        finally:
            ws.close()

    def test_t2_malformed_json_closes_silently(self):
        # pins current quirk, see docs/todo.md
        # T2: malformed JSON gets no reply at all; the handler logs the
        # exception and closes the websocket (fluxghost/api/touch.py
        # on_text_message).
        ws = WS(server.port, '/ws/touch')
        try:
            ws.send('this is not json {')
            self.assertTrue(ws.expect_closed())
        finally:
            ws.close()


if __name__ == '__main__':
    unittest.main()
