"""Usage tests for the image utility endpoints (cases U1-U3, O1 in docs/test-plan.md).

Covers /ws/utils commands the Beam Studio frontend actually calls
(`packages/core/src/web/helpers/api/utils-ws.ts`):

- U1 rgb_to_cmyk  (transformRgbImageToCmyk, resultType 'binary' — the frontend default)
- U2 split_color  (splitColor with colorType 'rgb' and 'cmy' — helpers/layer/full-color/splitColor.ts)
- U3 get_convex_hull (getConvexHull — helpers/device/framing.ts)

and the /ws/opencv upload+sharpen flow (`open-cv.ts`, Sharpen dialog):

- O1 upload → ok, sharpen → single binary PNG frame (need_upload when not cached)

Protocol reference: docs/api/utils.md and docs/api/opencv.md.
"""

import base64
import io
import json
import unittest

from PIL import Image, ImageDraw

from tests.usage._harness import WS, Server

SERVER = None

JPEG_MAGIC = b'\xff\xd8\xff'
PNG_MAGIC = b'\x89PNG\r\n\x1a\n'


def setUpModule():
    global SERVER
    SERVER = Server()


def tearDownModule():
    if SERVER is not None:
        SERVER.stop()


def make_png(size=(64, 64), bg=(255, 255, 255, 255), rect=None, fg=(200, 30, 30, 255)):
    """A small RGBA PNG (Beam Studio uploads RGBA blobs), optionally with a filled rectangle."""
    image = Image.new('RGBA', size, bg)
    if rect is not None:
        ImageDraw.Draw(image).rectangle(rect, fill=fg)
    out = io.BytesIO()
    image.save(out, format='PNG')
    return out.getvalue()


def read_binary(ws, length):
    """Collect binary frames until `length` bytes have arrived; return the bytes."""
    got = b''
    while len(got) < length:
        opcode, payload = ws.frame()
        if opcode == 2:
            got += payload
        elif opcode == 1:
            raise AssertionError('unexpected text frame while reading binary: %r' % payload)
    return got


class UtilsTest(unittest.TestCase):
    """U1-U3: /ws/utils commands as driven by utils-ws.ts."""

    def setUp(self):
        self.ws = WS(SERVER.port, '/ws/utils')
        self.addCleanup(self.ws.close)

    def upload(self, command, data, chunk_size=1000000):
        """Send `command`, wait for continue, stream `data` in frontend-sized chunks."""
        self.ws.send(command)
        self.ws.json_until(lambda m: m.get('status') == 'continue')
        for start in range(0, len(data), chunk_size):
            self.ws.send(data[start : start + chunk_size], opcode=2)

    def test_u1_rgb_to_cmyk_binary(self):
        """rgb_to_cmyk → uploaded → complete{length} → binary JPEG of exactly that length."""
        png = make_png(rect=(8, 8, 56, 56))
        self.upload('rgb_to_cmyk %d binary' % len(png), png)
        self.ws.json_until(lambda m: m.get('status') == 'uploaded')
        complete = self.ws.json_until(lambda m: m.get('status') == 'complete')
        self.assertIn('length', complete)
        self.assertGreater(complete['length'], 0)
        jpeg = read_binary(self.ws, complete['length'])
        self.assertEqual(len(jpeg), complete['length'])
        self.assertEqual(jpeg[:3], JPEG_MAGIC)

    def test_u1_rgb_to_cmyk_base64(self):
        """rgb_to_cmyk with result_type base64 → ok with a base64 JPEG in `data`."""
        png = make_png(rect=(8, 8, 56, 56))
        self.upload('rgb_to_cmyk %d base64' % len(png), png)
        self.ws.json_until(lambda m: m.get('status') == 'uploaded')
        ok = self.ws.json_until(lambda m: m.get('status') == 'ok')
        jpeg = base64.b64decode(ok['data'])
        self.assertEqual(jpeg[:3], JPEG_MAGIC)

    def test_u2_split_color(self):
        """split_color rgb → uploaded → ok with base64 JPEGs for each CMYK channel."""
        png = make_png(rect=(8, 8, 56, 56))
        # Chunk at 40 bytes to exercise the multi-frame upload path on a small image.
        self.upload('split_color %d rgb' % len(png), png, chunk_size=40)
        self.ws.json_until(lambda m: m.get('status') == 'uploaded')
        ok = self.ws.json_until(lambda m: m.get('status') == 'ok')
        for channel in ('c', 'm', 'y', 'k'):
            self.assertIn(channel, ok)
            jpeg = base64.b64decode(ok[channel])
            self.assertEqual(jpeg[:3], JPEG_MAGIC, 'channel %s is not a JPEG' % channel)

    def test_u2_split_color_cmy(self):
        """split_color cmy → the K channel comes back blank so no black ink is used."""
        png = make_png(rect=(8, 8, 56, 56))
        self.upload('split_color %d cmy' % len(png), png)
        self.ws.json_until(lambda m: m.get('status') == 'uploaded')
        ok = self.ws.json_until(lambda m: m.get('status') == 'ok')
        channels = {c: Image.open(io.BytesIO(base64.b64decode(ok[c]))) for c in ('c', 'm', 'y', 'k')}
        # 255 means no ink, so a blank K channel is all white
        self.assertEqual(channels['k'].convert('L').getextrema(), (255, 255))
        # the drawn rectangle still has to be printed by the remaining three
        self.assertLess(min(min(channels[c].convert('L').getextrema()) for c in ('c', 'm', 'y')), 250)

    def test_u2_split_color_cmy_from_cmyk_source(self):
        """A CMYK upload goes through the profile on its way to CMY, not PIL's own conversion."""
        cmyk = Image.new('CMYK', (32, 32))
        ImageDraw.Draw(cmyk).rectangle((4, 4, 28, 28), fill=(0, 0, 0, 200))  # dark grey, black ink only
        out = io.BytesIO()
        cmyk.save(out, format='JPEG')
        jpeg = out.getvalue()
        self.upload('split_color %d cmy' % len(jpeg), jpeg)
        self.ws.json_until(lambda m: m.get('status') == 'uploaded')
        ok = self.ws.json_until(lambda m: m.get('status') == 'ok')
        channels = {c: Image.open(io.BytesIO(base64.b64decode(ok[c]))) for c in ('c', 'm', 'y', 'k')}
        self.assertEqual(channels['k'].convert('L').getextrema(), (255, 255))
        # the black only rectangle has to come back as ink on all three remaining channels
        for name in ('c', 'm', 'y'):
            self.assertLess(min(channels[name].convert('L').getextrema()), 250, '%s channel is blank' % name)

    def test_u3_get_convex_hull(self):
        """get_convex_hull → ok with hull points covering the drawn shape, origin-nearest first."""
        png = make_png(size=(200, 150), rect=(40, 30, 160, 120), fg=(0, 0, 0, 255))
        self.upload('get_convex_hull %d' % len(png), png)
        ok = self.ws.json_until(lambda m: m.get('status') == 'ok')
        points = ok['data']
        self.assertGreaterEqual(len(points), 4)
        for point in points:
            self.assertEqual(len(point), 2)
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        # The hull should tightly bound the 40,30 → 160,120 rectangle (small tolerance).
        self.assertLessEqual(abs(min(xs) - 40), 3)
        self.assertLessEqual(abs(max(xs) - 160), 3)
        self.assertLessEqual(abs(min(ys) - 30), 3)
        self.assertLessEqual(abs(max(ys) - 120), 3)
        # The point list is rotated so the point nearest the origin comes first.
        dists = [p[0] * p[0] + p[1] * p[1] for p in points]
        self.assertEqual(dists[0], min(dists))

    def test_u3_get_convex_hull_blank_image(self):
        """A fully white image has no contours → ok with empty data."""
        png = make_png(size=(50, 50))
        self.upload('get_convex_hull %d' % len(png), png)
        ok = self.ws.json_until(lambda m: m.get('status') == 'ok')
        self.assertEqual(ok['data'], [])


class OpenCVTest(unittest.TestCase):
    """O1: /ws/opencv upload + sharpen as driven by open-cv.ts."""

    def setUp(self):
        self.ws = WS(SERVER.port, '/ws/opencv')
        self.addCleanup(self.ws.close)

    def test_o1_upload_then_sharpen(self):
        img_url = 'blob:file:///test-sharpen'
        # sharpen before upload → need_upload (the frontend relies on this to trigger upload).
        self.ws.send('sharpen %s 3.5 2' % img_url)
        self.ws.json_until(lambda m: m.get('status') == 'need_upload')
        # upload <url> <size> → continue → binary → ok
        png = make_png(rect=(8, 8, 56, 56))
        self.ws.send('upload %s %d' % (img_url, len(png)))
        self.ws.json_until(lambda m: m.get('status') == 'continue')
        self.ws.send(png, opcode=2)
        self.ws.json_until(lambda m: m.get('status') == 'ok')
        # sharpen → a single raw binary frame containing a PNG, no JSON preamble.
        self.ws.send('sharpen %s 3.5 2' % img_url)
        opcode, payload = self.ws.frame()
        detail = json.loads(payload) if opcode == 1 else opcode
        self.assertEqual(opcode, 2, 'expected a binary frame, got %r' % (detail,))
        self.assertEqual(payload[: len(PNG_MAGIC)], PNG_MAGIC)
        # The image stays cached: sharpen again with different params, no re-upload needed.
        self.ws.send('sharpen %s 5.0 4' % img_url)
        opcode, payload = self.ws.frame()
        self.assertEqual(opcode, 2)
        self.assertEqual(payload[: len(PNG_MAGIC)], PNG_MAGIC)


if __name__ == '__main__':
    unittest.main()
