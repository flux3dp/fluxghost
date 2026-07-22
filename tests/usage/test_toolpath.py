"""Usage tests P1-P10: /ws/svgeditor-laser-parser (see docs/test-plan.md).

Reproduces Beam Studio's real workflows from
beam-studio/packages/core/src/web/helpers/api/svg-laser-parser.ts:

- divide pipeline: ``upload_plain_svg`` + ``divide_svg``/``divide_svg_by_layer``
  (``uploadPlainSVG`` / ``divideSVG``)
- task pipeline: ``svgeditor_upload`` (128 KB chunks, thumbnail data-URI + SVG
  concatenated, ``uploadToSvgeditorAPI``) + ``go`` (``getTaskCode``) → FCode
- ``g2f`` gcode→FCode v1, ``set_params``, ``interrupt``

Protocol reference: docs/api/svgeditor-laser-parser.md.
"""

import json
import socket
import unittest

from tests.usage._harness import WS, Server

PATH = '/ws/svgeditor-laser-parser'

# Beam Studio sends svgeditor_upload/g2f payloads in 128 KB chunks
# (svg-laser-parser.ts: const CHUNK_SIZE = 128 * 1024).
CHUNK_SIZE = 128 * 1024

# The thumbnail part of svgeditor_upload/g2f payloads is a base64 PNG
# data-URI (SvgeditorImage._gen_thumbnail does thumbnail.split(b',') then
# b64decode). This is a valid 1x1 PNG.
THUMBNAIL = (
    b'data:image/png;base64,'
    b'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=='
)

# Plain SVG for the divide pipeline (same shape as tools/ws_smoke.py).
SMOKE_SVG = (
    b'<?xml version="1.0" encoding="utf-8"?>'
    b'<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100" viewBox="0 0 100 100">'
    b'<rect x="10" y="10" width="50" height="30" fill="none" stroke="#000000"/>'
    b'</svg>'
)

# Two-layer plain SVG so divide_svg_by_layer produces named layer parts.
LAYERED_PLAIN_SVG = (
    b'<?xml version="1.0" encoding="utf-8"?>'
    b'<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100" viewBox="0 0 100 100">'
    b'<g class="layer"><title>LayerA</title>'
    b'<rect x="10" y="10" width="50" height="30" fill="none" stroke="#ff0000"/></g>'
    b'<g class="layer"><title>LayerB</title>'
    b'<circle cx="60" cy="60" r="20" fill="none" stroke="#0000ff"/></g>'
    b'</svg>'
)

# Beam Studio scene SVG for the task pipeline: root children are
# <g class="layer"> groups carrying data-* config attributes
# (fluxclient/toolpath/svgeditor_factory.py SvgeditorImage._get_layer_params);
# 10 px per mm (-mdpi / -dpmm 10), fbb1b workarea is 400x375 mm.
BEAM_SCENE_SVG = (
    b'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
    b'width="4000" height="3750" viewBox="0 0 4000 3750">'
    b'<g class="layer" data-color="#333333" data-strength="15" data-speed="20" data-repeat="1">'
    b'<title>Layer 1</title>'
    b'<rect x="100" y="100" width="200" height="150" fill="none" stroke="#333333" stroke-width="1"/>'
    b'</g>'
    b'</svg>'
)

# Heavier scene for the interrupt test: a 200x200 mm filled rect engraved 6
# times -> `go` needs ~2 s uninterrupted, a wide window for `interrupt`.
BIG_SCENE_SVG = (
    b'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
    b'width="4000" height="3750" viewBox="0 0 4000 3750">'
    b'<g class="layer" data-color="#333333" data-strength="30" data-speed="100" data-repeat="6">'
    b'<title>Layer 1</title>'
    b'<rect x="100" y="100" width="2000" height="2000" fill="#000000"/>'
    b'</g>'
    b'</svg>'
)

# Exact flag strings Beam Studio builds for a Beambox (fbb1b) task:
# - uploadToSvgeditorAPI: [orderName, name, size, thumbSize] + legacy
#   '-<model>' + '-model <model>' + dpi flag + '-dpmm <n>'
#   (no -workarea: only sent when the workarea is expanded)
# - getTaskCode: ['go', name, '-f'] + getExportOpt args: legacy hardware
#   name ('-beambox'), '-model fbb1b', '-min-speed <workarea minSpeed>'
UPLOAD_FLAGS = '-fbb1b -model fbb1b -mdpi -dpmm 10'
GO_FLAGS = '-f -beambox -model fbb1b -min-speed 3'

SERVER = None


def setUpModule():
    global SERVER
    SERVER = Server()
    try:
        probe = WS(SERVER.port, PATH)
        probe.close()
    except ConnectionError as e:
        SERVER.stop()
        SERVER = None
        raise unittest.SkipTest('svgeditor-laser-parser route unavailable (fluxsvg/beamify missing?): %s' % e)


def tearDownModule():
    if SERVER is not None:
        SERVER.stop()


class ToolpathTest(unittest.TestCase):
    """P1-P10: svgeditor-laser-parser protocol as driven by svg-laser-parser.ts."""

    def setUp(self):
        self.ws = WS(SERVER.port, PATH, timeout=120)
        self.addCleanup(self.ws.close)

    # -- helpers ----------------------------------------------------------

    def send_chunked(self, payload):
        """Send a binary payload in 128 KB chunks like the frontend."""
        for i in range(0, len(payload), CHUNK_SIZE):
            self.ws.send(payload[i : i + CHUNK_SIZE], opcode=2)

    def upload_plain_svg(self, svg, name='plain-svg', chunked=False):
        self.ws.send('upload_plain_svg %s %d' % (name, len(svg)))
        self.ws.json_until(lambda m: m.get('status') == 'continue')
        if chunked:
            self.send_chunked(svg)
        else:
            self.ws.send(svg, opcode=2)
        self.ws.json_until(lambda m: m.get('status') == 'ok')

    def svgeditor_upload(self, svg, name='scene.svg', flags=UPLOAD_FLAGS):
        """Real Beam Studio upload: <thumbnail data-URI><svg> in 128 KB chunks."""
        payload = THUMBNAIL + svg
        self.ws.send('svgeditor_upload %s %d %d %s' % (name, len(payload), len(THUMBNAIL), flags))
        self.ws.json_until(lambda m: m.get('status') == 'continue')
        self.send_chunked(payload)
        statuses = []
        msg = self.ws.json_until(
            lambda m: statuses.append(m.get('status')) or m.get('status') != 'computing',
            max_frames=500,
        )
        self.assertEqual(msg.get('status'), 'ok', 'upload failed: %s' % msg)
        # anything before the ok must be analyzing-progress
        self.assertEqual(set(statuses[:-1]) - {'computing'}, set())
        return msg

    def read_divide_parts(self, max_frames=100):
        """Collect (header, binary) parts until {"status": "ok"} (divideSVG)."""
        parts = []
        current = None
        for _ in range(max_frames):
            op, payload = self.ws.frame()
            if op == 1:
                msg = json.loads(payload)
                if msg.get('status') == 'ok':
                    self.assertIsNone(current, 'ok arrived mid-part')
                    return parts
                self.assertNotIn(msg.get('status'), ('Error', 'error', 'fatal'), 'divide failed: %s' % msg)
                self.assertIn('name', msg)
                current = (msg, bytearray())
            elif op in (0, 2) and current is not None:
                current[1].extend(payload)
                if len(current[1]) >= current[0]['length']:
                    parts.append((current[0], bytes(current[1])))
                    current = None
        self.fail('no ok after %d frames; got parts %r' % (max_frames, [p[0] for p in parts]))

    def run_go(self, flags=GO_FLAGS, name='scene.svg'):
        """Send `go` and return (complete_msg, binary). Frontend: getTaskCode."""
        self.ws.send('go %s %s' % (name, flags))
        statuses = []
        msg = self.ws.json_until(lambda m: statuses.append(m) or m.get('status') != 'computing', max_frames=1000)
        self.assertEqual(msg.get('status'), 'complete', 'go failed: %s' % msg)
        computing = statuses[:-1]
        self.assertTrue(computing, 'expected progress before complete')
        self.assertTrue(all(m.get('status') == 'computing' for m in computing))
        self.assertIn('initializing', [m.get('translation_key') for m in computing])
        # accumulate binary frames until the announced length (like the frontend)
        binary = bytearray()
        while len(binary) < msg['length']:
            op, payload = self.ws.frame()
            if op in (0, 2):
                binary.extend(payload)
        self.assertEqual(len(binary), msg['length'])
        return msg, bytes(binary)

    # -- P1/P2: upload_plain_svg ------------------------------------------

    def test_p01_upload_plain_svg_single_frame(self):
        # continue/ok asserted inside the helper
        self.upload_plain_svg(SMOKE_SVG, name='smoke.svg')

    def test_p02_upload_plain_svg_chunked_128kb(self):
        # pad past 128 KB so the frontend-style chunking actually splits
        padding = b'<!-- ' + b'x' * (CHUNK_SIZE + 4096) + b' -->'
        svg = SMOKE_SVG.replace(b'</svg>', padding + b'</svg>')
        self.assertGreater(len(svg), CHUNK_SIZE)
        self.upload_plain_svg(svg, chunked=True)

    # -- P3/P4: divide_svg -------------------------------------------------

    def test_p03_divide_svg(self):
        self.upload_plain_svg(LAYERED_PLAIN_SVG)
        self.ws.send('divide_svg')
        parts = self.read_divide_parts()
        names = [header['name'] for header, _ in parts]
        self.assertEqual(names, ['strokes', 'bitmap', 'colors'])
        by_name = {header['name']: (header, data) for header, data in parts}
        self.assertGreater(by_name['strokes'][0]['length'], 0)
        self.assertIn(b'<svg', by_name['strokes'][1])
        # vector-only scene: no bitmap part, no offset field
        self.assertEqual(by_name['bitmap'][0]['length'], 0)
        self.assertNotIn('offset', by_name['bitmap'][0])
        self.assertGreater(by_name['colors'][0]['length'], 0)
        for header, data in parts:
            self.assertEqual(len(data), header['length'])

    def test_p04_divide_svg_scaled(self):
        self.upload_plain_svg(LAYERED_PLAIN_SVG)
        self.ws.send('divide_svg -s 2')
        parts = self.read_divide_parts()
        names = [header['name'] for header, _ in parts]
        self.assertEqual(names, ['strokes', 'bitmap', 'colors'])
        for header, data in parts:
            self.assertEqual(len(data), header['length'])

    # -- P5: divide_svg_by_layer -------------------------------------------

    def test_p05_divide_svg_by_layer(self):
        self.upload_plain_svg(LAYERED_PLAIN_SVG)
        self.ws.send('divide_svg_by_layer')
        parts = self.read_divide_parts()
        names = [header['name'] for header, _ in parts]
        # nolayer and bitmap are sent twice: once explicitly, then again by
        # the generic key loop -- pins current quirk, see docs/todo.md
        self.assertEqual(names[:4], ['nolayer', 'bitmap', 'nolayer', 'bitmap'])
        # then one part per layer, named by the layer <title>
        self.assertEqual(names[4:], ['LayerA', 'LayerB'])
        by_name = {header['name']: (header, data) for header, data in parts}
        self.assertIn(b'<svg', by_name['LayerA'][1])
        self.assertIn(b'<svg', by_name['LayerB'][1])
        self.assertEqual(by_name['bitmap'][0]['length'], 0)

    # -- P6: set_params ------------------------------------------------------

    def test_p06_set_params_loop_compensation(self):
        # Beam Studio: setParameter('loop_compensation', n) right before go
        self.ws.send('set_params loop_compensation 0.5')
        msg = self.ws.json_until(lambda m: 'status' in m)
        self.assertEqual(msg['status'], 'ok')

    # -- P7/P8: svgeditor_upload + go (the real Beam Studio export flow) ----

    def test_p07_svgeditor_upload_layered_scene(self):
        self.svgeditor_upload(BEAM_SCENE_SVG)

    def test_p08_go_produces_fcode(self):
        # full frontend export sequence on one socket:
        # set_params loop_compensation -> svgeditor_upload -> go
        self.ws.send('set_params loop_compensation 0')
        self.ws.json_until(lambda m: m.get('status') == 'ok')
        self.svgeditor_upload(BEAM_SCENE_SVG)

        msg, fcode = self.run_go()
        # fbb1b -> FCode v1 (FCODE_VERSION_MAP), magic forced to 1
        self.assertTrue(fcode.startswith(b'FCx'), 'bad magic: %r' % fcode[:8])
        self.assertTrue(fcode.startswith(b'FCx0001'), 'expected FCode v1: %r' % fcode[:8])
        self.assertGreater(msg['time'], 0)
        self.assertGreater(msg['traveled_dist'], 0)
        metadata = msg['metadata']
        self.assertEqual(metadata.get('HEAD_TYPE'), 'LASER')
        self.assertEqual(metadata.get('START_WITH_HOME'), '1')
        self.assertIn('TIME_COST', metadata)

    # -- P9: g2f -------------------------------------------------------------

    def test_p09_g2f_gcode_to_fcode(self):
        # get real gcode the way the frontend can: go with -gc outputs gcode
        self.svgeditor_upload(BEAM_SCENE_SVG)
        msg, gcode = self.run_go(flags=GO_FLAGS + ' -gc')
        # gcode mode: time/traveled_dist are 0 and metadata is empty
        self.assertEqual(msg['time'], 0)
        self.assertEqual(msg['metadata'], {})
        self.assertIn(b'G1', gcode)

        # g2f payload = <base64 PNG data-URI thumbnail><gcode>
        payload = THUMBNAIL + gcode
        self.ws.send('g2f %d %d' % (len(payload), len(THUMBNAIL)))
        self.ws.json_until(lambda m: m.get('status') == 'continue')
        self.send_chunked(payload)
        self.ws.json_until(lambda m: m.get('status') == 'ok')
        statuses = []
        msg = self.ws.json_until(lambda m: statuses.append(m) or m.get('status') != 'computing', max_frames=1000)
        self.assertEqual(msg.get('status'), 'complete', 'g2f failed: %s' % msg)
        # unlike go, the g2f complete message carries no metadata field
        self.assertNotIn('metadata', msg)
        fcode = bytearray()
        while len(fcode) < msg['length']:
            op, payload = self.ws.frame()
            if op in (0, 2):
                fcode.extend(payload)
        # g2f is always FCode v1
        self.assertTrue(fcode.startswith(b'FCx0001'), 'bad magic: %r' % bytes(fcode[:8]))

    # -- P10: interrupt --------------------------------------------------------

    def test_p10_interrupt_stops_go(self):
        # Message handling is threaded (svgeditor_toolpath._handle_message), so
        # `interrupt` is processed while `go` computes. The scene is sized so an
        # uninterrupted go takes ~2 s while the interrupt lands within
        # milliseconds of the first progress message -- deterministic in
        # practice. An interrupted go stops silently: no complete, no binary.
        self.svgeditor_upload(BIG_SCENE_SVG)
        self.ws.send('go scene.svg %s' % GO_FLAGS)
        self.ws.json_until(lambda m: m.get('status') == 'computing')
        self.ws.send('interrupt')

        # The interrupt ack and go's progress frames are written by two server
        # threads without a send lock (fluxghost/utils/websocket.py:_send emits
        # the 2-byte header and the payload as separate send() calls), so the
        # frame stream can interleave and defeat a frame-level parser -- pins
        # current quirk, see docs/todo.md. Beam Studio never notices because it
        # discards the socket right after interrupting (resetWebsocket). Each
        # payload < 4 KB is still written by a single send() call, so scan the
        # raw byte stream for the payloads instead of parsing frames.
        data = bytes(self.ws.buf)
        self.ws.buf = b''
        self.ws.sock.settimeout(6)
        try:
            while True:
                chunk = self.ws.sock.recv(65536)
                if not chunk:
                    break
                data += chunk
        except socket.timeout:
            pass  # went quiet: the interrupted go stopped without replying
        self.assertIn(b'{"status": "ok"}', data, 'interrupt was not acknowledged: %r' % data[-200:])
        self.assertNotIn(b'"status": "complete"', data, 'go finished despite interrupt')
        self.assertNotIn(b'FCx', data, 'FCode was streamed despite interrupt')


if __name__ == '__main__':
    unittest.main()
