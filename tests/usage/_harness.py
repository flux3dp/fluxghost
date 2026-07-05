"""Shared harness for the usage-based protocol tests (see docs/test-plan.md).

Spawns a real `ghost.py -d --port 0` server per test module and provides a
stdlib-only websocket client. Python 3.8 compatible; no external deps
(pycryptodome is optional, only needed by tests that authenticate).
"""

import base64
import contextlib
import json
import os
import socket
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SIM_UUID = '0' * 32


class Server:
    """A fluxghost process on an auto-assigned port. Use as a module fixture."""

    def __init__(self, extra_args=None):
        env = dict(os.environ)
        if sys.platform == 'darwin' and 'DYLD_FALLBACK_LIBRARY_PATH' not in env:
            env['DYLD_FALLBACK_LIBRARY_PATH'] = '/opt/homebrew/lib'
        args = [sys.executable, os.path.join(ROOT, 'ghost.py'), '-d', '--port', '0']
        if extra_args:
            args += list(extra_args)
        self.proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, cwd=ROOT, env=env)
        self.port = self._wait_ready()

    def _wait_ready(self, timeout=20):
        deadline = time.time() + timeout
        while time.time() < deadline:
            line = self.proc.stdout.readline()
            if not line:
                break
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if msg.get('type') == 'ready':
                return msg['port']
        self.stop()
        raise RuntimeError('server did not print the ready line within %ss' % timeout)

    def stop(self):
        with contextlib.suppress(OSError):
            self.proc.terminate()
        with contextlib.suppress(Exception):
            self.proc.wait(timeout=10)


class WS:
    """Minimal RFC 6455 websocket client (client frames masked, server frames not)."""

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
            raise ConnectionError('handshake failed for %s: %r' % (path, status))
        self.buf = buf.split(b'\r\n\r\n', 1)[1]

    def _fill(self, n):
        while len(self.buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise EOFError('connection closed')
            self.buf += chunk

    def frame(self):
        """Return (opcode, payload) of the next frame. opcode 1=text, 2=binary, 8=close."""
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

    def json_until(self, pred, max_frames=60):
        """Read frames until a text frame's JSON satisfies pred; return that message."""
        for _ in range(max_frames):
            op, payload = self.frame()
            if op != 1:
                continue
            msg = json.loads(payload)
            if pred(msg):
                return msg
        raise AssertionError('expected message not received within %d frames' % max_frames)

    def expect_closed(self, timeout=5):
        """Return True if the server closes the connection (close frame or EOF).

        A quiet socket (timeout with no close) returns False — "the server
        stopped talking" must not pass as "the server closed".
        """
        self.sock.settimeout(timeout)
        try:
            while True:
                op, _ = self.frame()
                if op == 8:
                    return True
        except socket.timeout:
            return False
        except (EOFError, ConnectionError, OSError):
            return True

    def close(self):
        with contextlib.suppress(OSError):
            self.sock.close()


def make_rsa_pem():
    """A fresh RSA private key PEM, or None if pycryptodome is unavailable."""
    try:
        from Crypto.PublicKey import RSA
    except ImportError:
        return None
    return RSA.generate(1024).export_key().decode()
