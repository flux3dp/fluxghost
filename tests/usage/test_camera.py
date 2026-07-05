"""Camera endpoint tests — cases M1-M3 in docs/test-plan.md.

Beam Studio's `camera.ts` opens `/ws/camera/<uuid>`, sends its RSA key and
then consumes auto-pushed binary frames. With the simulated device (`-d`)
the camera pushes the same PNG file every 0.25 s (fluxghost/simulate/camera.py).
"""

import time
import unittest

from tests.usage._harness import SIM_UUID, WS, Server, make_rsa_pem

PNG_MAGIC = b'\x89PNG'

_server = None
_pem = None


def setUpModule():
    global _server, _pem
    _pem = make_rsa_pem()
    if _pem is None:
        raise unittest.SkipTest('pycryptodome not installed; cannot build an RSA key')
    _server = Server()


def tearDownModule():
    if _server is not None:
        _server.stop()


def connect_camera():
    """Open the camera websocket, authenticate, and return (ws, stages).

    `stages` is the list of `{"status": "connecting", "stage": ...}` stage
    names received before `{"status": "connected"}` (control_base.py emits
    discover/connecting for uuid targets). Retries a few times in case the
    simulated device has not hit the discover cache yet (NOT_FOUND fatal).
    """
    last_fatal = None
    for _ in range(10):
        ws, stages, outcome = _attempt_handshake()
        if outcome.get('status') == 'connected':
            return ws, stages
        last_fatal = outcome
        ws.close()
        time.sleep(0.5)
    raise AssertionError('camera handshake kept failing, last fatal: %r' % (last_fatal,))


def _attempt_handshake():
    """One handshake attempt: returns (ws, stage names, connected/fatal message)."""
    ws = WS(_server.port, '/ws/camera/' + SIM_UUID)
    ws.send(_pem)
    stages = []
    outcome = {}

    def pred(msg):
        status = msg.get('status')
        if status == 'connecting':
            stages.append(msg.get('stage'))
            return False
        if status in ('connected', 'fatal'):
            outcome.update(msg)
            return True
        return False

    ws.json_until(pred)
    return ws, stages, outcome


def collect_binary_frames(ws, count, max_frames=100):
    """Read frames until `count` binary payloads are collected (bounded)."""
    frames = []
    for _ in range(max_frames):
        opcode, payload = ws.frame()
        if opcode == 2:
            frames.append(payload)
            if len(frames) == count:
                return frames
    raise AssertionError('only %d/%d binary frames within %d websocket frames' % (len(frames), count, max_frames))


class CameraHandshakeTest(unittest.TestCase):
    def test_m1_handshake_reaches_connected(self):
        ws, stages = connect_camera()
        try:
            # connect_camera only returns once {"status": "connected"} arrived;
            # the uuid path in control_base.py emits both stages first.
            self.assertEqual(stages, ['discover', 'connecting'])
        finally:
            ws.close()


class CameraFramesTest(unittest.TestCase):
    def test_m2_auto_pushed_png_frames(self):
        ws, _ = connect_camera()
        try:
            frames = collect_binary_frames(ws, 2)
        finally:
            ws.close()
        for frame in frames:
            self.assertEqual(frame[:4], PNG_MAGIC)
        # The simulator pushes the same file every time.
        self.assertEqual(len(frames[0]), len(frames[1]))

    def test_m3_sustained_frame_cadence(self):
        ws, _ = connect_camera()
        try:
            start = time.monotonic()
            frames = collect_binary_frames(ws, 4)
            elapsed = time.monotonic() - start
        finally:
            ws.close()
        self.assertEqual(len(frames), 4)
        # Simulator cadence is 4 fps (one frame per 0.25 s); 4 frames should
        # take ~0.75 s. Loose bounds: not a burst, not a stall (CI jitter).
        self.assertGreaterEqual(elapsed, 0.5)
        self.assertLessEqual(elapsed, 4.0)


if __name__ == '__main__':
    unittest.main()
