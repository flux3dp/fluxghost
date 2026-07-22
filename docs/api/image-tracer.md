# Image Tracer

`ws://127.0.0.1:8000/ws/image-tracer`

Bitmap-to-vector tracing: upload an image and a black/white threshold, get back a single-path outline SVG string. The tracer binarizes the image, walks its edge pixels into an ordered path, and emits the longest closed outline it finds.

- **Handler**: `fluxghost/api/image_tracer.py` (`image_tracer_api_mixin`), wrapper `fluxghost/websocket/image_tracer.py`, route `fluxghost/http_websocket_route.py:26` - **Beam Studio client**: none found — no code in `beam-studio/packages/core/src/web` opens a `image-tracer` websocket. Beam Studio traces images client-side with the `imagetracerjs` library in a web worker (`packages/core/src/web/helpers/image-tracer/image-tracer.worker.ts`, spawned from `helpers/image-edit.ts`).

## Connection

No URL parameters. Commands are plain-text frames `<cmd> <params...>` dispatched via `cmd_mapping` (`fluxghost/api/image_tracer.py:19`, `fluxghost/api/misc.py:29-56`). The handler is stateless apart from the pending binary upload. Only one command exists.

## Commands

### `image_trace <file_size> <threshold>`

Starts a binary upload of `file_size` bytes, then traces the image (`fluxghost/api/image_tracer.py:21-32`).

- `file_size` — byte length of the image that will be streamed.
- `threshold` — int, black/white cutoff (pixels with `max(r, g, b)` below it become black, others white; `moderateBinary`, `fluxghost/api/image_tracer.py:62-85`).

```
→ image_trace 152833 128
← {"status": "continue"}
→ <binary chunks totalling 152833 bytes>
← {"status": "ok", "svg": "<svg width=\"800\" height=\"600\" xmlns=\"http://www.w3.org/2000/svg\"><g><path d=\"M12 15 13 15 ... \" fill=\"none\" stroke-width=\"1px\" stroke=\"rgb(100%, 0%, 100%)\" vector-effect=\"non-scaling-stroke\" transform=\"scale(2.5)\" /></g></svg>"}
```

The upload follows the standard `BinaryUploadHelper` flow (`fluxghost/api/misc.py:59-89`): after `{"status": "continue"}`, stream raw binary frames until exactly `file_size` bytes have arrived; the trace then runs synchronously and the only success response is the `{"status": "ok", "svg": ...}` frame. There are no progress messages.

What `run()` does (`fluxghost/api/image_tracer.py:244-304`):

1. Opens the upload with PIL and converts it to RGBA.
2. Resizes to 40% of the original size (`ratio = 0.4`, bilinear).
3. Binarizes each pixel against `threshold` (`moderateBinary`).
4. Labels the background with `scipy.ndimage.label` and collects every pixel bordering the background region as an edge point (`fill` / `isEdge`, `fluxghost/api/image_tracer.py:34-48`, `106-119`).
5. Sorts edge points into connected paths by walking neighbors (`sortEdges`), repeating with the leftover points until all edges are consumed or no progress is made.
6. Picks the **longest** path only — inner holes and smaller disjoint shapes are discarded.
7. Builds the SVG string: `width`/`height` are the **original** image dimensions, the path data is one `M` command followed by the traced point coordinates (in the 40%-scale coordinate system), stroked magenta (`rgb(100%, 0%, 100%)`) with `transform="scale(2.5)"` to map back to full size (0.4 × 2.5 = 1).

## Errors

- Unknown command or non-integer `file_size`/`threshold` (`ValueError`) → `{"status": "Error", "message": "BAD_PARAM_TYPE"}` — capitalized `Error` (`fluxghost/api/misc.py:50-52`).
- Text frame while the upload is in progress → `{"status": "fatal", "symbol": ["PROTOCOL_ERROR"], "error": "PROTOCOL_ERROR"}` (`fluxghost/api/misc.py:48`).
- Binary frame with no upload pending → fatal `BAD_PROTOCOL`; more bytes than declared → fatal `BAD_LENGTH...` (`fluxghost/api/misc.py:17-27`, `86-89`).
- The trace callback has no try/except: an undecodable image (or any tracing failure) raises an uncaught exception and no response frame is sent.

## Example Session

```
→ image_trace 152833 128
← {"status": "continue"}
→ <binary: 152833 bytes of PNG>
← {"status": "ok", "svg": "<svg width=\"800\" height=\"600\" ...>...</svg>"}
```

## Notes

- The route path is `image-tracer` (hyphen); the JavaScript example in the wrapper's docstring (`fluxghost/websocket/image_tracer.py:9`) shows `ws/image_tracer` (underscore), which does **not** match the route regex.
- `run()` accepts a `milli` border-expansion parameter but is always called with the default `0` (`fluxghost/api/image_tracer.py:26`, `244`), so the border-expansion step (`borderExpandList`) adds nothing.
- The trace is pure-Python and iterates every pixel of the 40%-scaled image several times; large uploads block the handler for the duration.
- The tracer keys off the **red channel** after binarization (`makePixList` stores only `r`, `fluxghost/api/image_tracer.py:93-104`); binarization writes pure black/white so this is equivalent to luminance for its own output.
- Since no Beam Studio code connects to this endpoint, it is effectively legacy; the in-app "trace image" feature runs `imagetracerjs` locally instead.
