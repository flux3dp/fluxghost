#!/usr/bin/env python3
"""Websocket smoke tests for fluxghost. No hardware, no external deps.

Usage:
    uv run python tools/ws_smoke.py

Spawns `ghost.py -d --port 0` (the -d flag registers the simulated device,
uuid 00000000000000000000000000000000), discovers the port from the
`{"type": "ready", "port": N}` stdout line — the same contract Beam Studio's
backend-manager.ts relies on — then exercises every endpoint that works
without a machine:

    ver        version push on connect
    discover   simulated device announcement
    touch      uuid=0 auth shortcut
    control    RSA handshake, `file ls SD`, `play report`
    camera     binary PNG frame streaming
    toolpath   upload_plain_svg + divide_svg  (skipped if fluxsvg missing —
               a SKIP is NOT a pass when you changed toolpath code)

Exit code 0 = all executed checks passed. Any FAIL = exit 1.
"""

import base64
import contextlib
import json
import os
import socket
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIM_UUID = '0' * 32
RESULTS = []  # (name, 'PASS' | 'FAIL' | 'SKIP', detail)


def record(name, ok, detail=''):
    RESULTS.append((name, 'PASS' if ok else 'FAIL', detail))
    print('%-4s %s %s' % ('PASS' if ok else 'FAIL', name, detail))


def skip(name, reason):
    RESULTS.append((name, 'SKIP', reason))
    print('SKIP %s (%s)' % (name, reason))


class WS:
    """Minimal RFC 6455 client, stdlib only."""

    def __init__(self, port, path, timeout=15):
        self.sock = socket.create_connection(('127.0.0.1', port), timeout=timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall(
            (
                'GET %s HTTP/1.1\r\nHost: 127.0.0.1:%d\r\n'
                'Upgrade: websocket\r\nConnection: Upgrade\r\n'
                'Sec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\n'
                'Origin: http://127.0.0.1\r\n\r\n' % (path, port, key)
            ).encode()
        )
        buf = b''
        while b'\r\n\r\n' not in buf:
            buf += self.sock.recv(4096)
        status = buf.split(b'\r\n', 1)[0]
        if b'101' not in status:
            raise AssertionError('handshake failed for %s: %r' % (path, status))
        self.buf = buf.split(b'\r\n\r\n', 1)[1]

    def _fill(self, n):
        while len(self.buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise EOFError('connection closed')
            self.buf += chunk

    def frame(self):
        """Return (opcode, payload) of the next frame (server frames are unmasked)."""
        self._fill(2)
        opcode = self.buf[0] & 0x0F
        length = self.buf[1] & 0x7F
        off = 2
        if length == 126:
            self._fill(4)
            length = int.from_bytes(self.buf[2:4], 'big')
            off = 4
        elif length == 127:
            self._fill(10)
            length = int.from_bytes(self.buf[2:10], 'big')
            off = 10
        self._fill(off + length)
        payload = self.buf[off : off + length]
        self.buf = self.buf[off + length :]
        return opcode, payload

    def send(self, payload, opcode=1):
        if isinstance(payload, str):
            payload = payload.encode()
        header = bytes([0x80 | opcode])
        mask = os.urandom(4)
        n = len(payload)
        if n < 126:
            header += bytes([0x80 | n])
        elif n < 65536:
            header += bytes([0x80 | 126]) + n.to_bytes(2, 'big')
        else:
            header += bytes([0x80 | 127]) + n.to_bytes(8, 'big')
        self.sock.sendall(header + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))

    def json_until(self, pred, max_frames=40):
        for _ in range(max_frames):
            op, payload = self.frame()
            if op != 1:
                continue
            msg = json.loads(payload)
            if pred(msg):
                return msg
        raise AssertionError('expected message not received within %d frames' % max_frames)

    def close(self):
        with contextlib.suppress(OSError):
            self.sock.close()


def start_server():
    env = dict(os.environ)
    if sys.platform == 'darwin' and 'DYLD_FALLBACK_LIBRARY_PATH' not in env:
        env['DYLD_FALLBACK_LIBRARY_PATH'] = '/opt/homebrew/lib'  # arm64: lib/mac dylibs are x86_64-only
    proc = subprocess.Popen(
        [sys.executable, os.path.join(ROOT, 'ghost.py'), '-d', '--port', '0'],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        cwd=ROOT,
        env=env,
    )
    deadline = time.time() + 20
    while time.time() < deadline:
        line = proc.stdout.readline()
        if not line:
            break
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        if msg.get('type') == 'ready':
            return proc, msg['port']
    proc.terminate()
    raise RuntimeError('server did not print the {"type": "ready"} line within 20s')


def make_rsa_pem():
    try:
        from Crypto.PublicKey import RSA
    except ImportError:
        return None
    return RSA.generate(1024).export_key().decode()


def check_ver(port):
    ws = WS(port, '/ws/ver')
    op, payload = ws.frame()
    msg = json.loads(payload)
    record('ver', 'fluxghost' in msg and 'fluxclient' in msg, json.dumps(msg))
    ws.close()


def check_discover(port):
    ws = WS(port, '/ws/discover')
    dev = ws.json_until(lambda m: m.get('uuid') == SIM_UUID)
    record('discover', dev.get('alive') is True and dev.get('model') == 'simulate', 'name=%r' % dev.get('name'))
    ws.close()


def check_touch(port, pem):
    ws = WS(port, '/ws/touch')
    ws.send(json.dumps({'key': pem, 'uuid': SIM_UUID, 'password': ''}))
    op, payload = ws.frame()
    msg = json.loads(payload)
    record('touch', msg.get('auth') is True and msg.get('serial') == 'SIMULATE00', json.dumps(msg))
    ws.close()


def check_control(port, pem):
    ws = WS(port, '/ws/control/' + SIM_UUID)
    ws.send(pem)
    msg = ws.json_until(lambda m: m.get('status') in ('connected', 'error', 'fatal'))
    record('control.connect', msg.get('status') == 'connected', json.dumps(msg))

    ws.send('file ls SD')
    files = None
    for _ in range(10):
        op, payload = ws.frame()
        msg = json.loads(payload)
        if 'files' in msg:
            files = msg['files']
        if msg.get('status') == 'ok':
            break
    record('control.file_ls', files is not None, 'files=%s' % files)

    ws.send('play report')
    msg = ws.json_until(lambda m: m.get('status') == 'ok')
    record('control.play_report', msg.get('device_status', {}).get('st_label') == 'IDLE', json.dumps(msg))

    ws.send('kick')
    ws.close()


def check_camera(port, pem):
    ws = WS(port, '/ws/camera/' + SIM_UUID)
    ws.send(pem)
    ws.json_until(lambda m: m.get('status') == 'connected')
    frame = None
    for _ in range(20):
        op, payload = ws.frame()
        if op == 2 and payload:
            frame = payload
            break
    record('camera.frame', frame is not None and frame[:4] == b'\x89PNG', 'len=%s' % (len(frame) if frame else 0))
    ws.close()


def check_toolpath(port):
    svg = (
        b'<?xml version="1.0" encoding="utf-8"?>'
        b'<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100" viewBox="0 0 100 100">'
        b'<rect x="10" y="10" width="50" height="30" fill="none" stroke="#000000"/>'
        b'</svg>'
    )
    try:
        ws = WS(port, '/ws/svgeditor-laser-parser')
    except (AssertionError, EOFError, OSError) as e:
        skip('toolpath', 'route unavailable — fluxsvg/beamify/cairo missing on server (%s)' % e)
        return
    ws.send('upload_plain_svg smoke.svg %d' % len(svg))
    ws.json_until(lambda m: m.get('status') == 'continue')
    ws.send(svg, opcode=2)
    ws.json_until(lambda m: m.get('status') == 'ok')

    ws.send('divide_svg')
    parts = []
    ok = False
    for _ in range(20):
        op, payload = ws.frame()
        if op == 1:
            msg = json.loads(payload)
            if 'name' in msg:
                parts.append(msg['name'])
            if msg.get('status') == 'ok':
                ok = True
                break
            if msg.get('status') in ('Error', 'error', 'fatal'):
                break
    record('toolpath.divide_svg', ok and 'strokes' in parts, 'parts=%s' % parts)
    ws.close()


def main():
    proc, port = start_server()
    print('server ready on port %d' % port)
    try:
        check_ver(port)
        check_discover(port)

        pem = make_rsa_pem()
        if pem is None:
            skip('touch', 'pycryptodome not installed')
            skip('control', 'pycryptodome not installed')
            skip('camera', 'pycryptodome not installed')
        else:
            check_touch(port, pem)
            check_control(port, pem)
            check_camera(port, pem)

        check_toolpath(port)
    finally:
        proc.terminate()

    passed = sum(1 for _, s, _ in RESULTS if s == 'PASS')
    failed = sum(1 for _, s, _ in RESULTS if s == 'FAIL')
    skipped = sum(1 for _, s, _ in RESULTS if s == 'SKIP')
    print('\n%d passed, %d failed, %d skipped' % (passed, failed, skipped))
    if failed:
        sys.exit(1)
    print('ALL PASS')


if __name__ == '__main__':
    main()
