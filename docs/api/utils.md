# Utils

`ws://127.0.0.1:8000/ws/utils`

General-purpose image/file utility endpoint: PDF→SVG conversion, file uploads to local paths, font installation, RGB→CMYK conversion, CMYK channel splitting, and OpenCV contour analysis (auto-fit and convex hull).

- **Handler**: `fluxghost/api/utils.py` (`utils_api_mixin`), wrapper `fluxghost/websocket/utils.py`, route `fluxghost/http_websocket_route.py:30` - **Beam Studio client**: `packages/core/src/web/helpers/api/utils-ws.ts` (`UtilsWebSocket` singleton)

## Connection

No URL parameters. Commands are plain-text frames of the form `<cmd> <params...>` — the first whitespace-separated token is the command, the rest is passed as a single params string (`fluxghost/api/misc.py:29-56`). Most commands start a binary upload: the server replies `{"status": "continue"}`, then the client streams raw binary frames until exactly the declared byte count has arrived (`BinaryUploadHelper`, `fluxghost/api/misc.py:59-89`). Beam Studio chunks uploads at 1,000,000 bytes per frame. Sending a text frame while an upload is in progress is a fatal protocol error.

## Commands

### `pdf2svg <file_size>`

Upload a PDF, get SVG back (`fluxghost/api/utils.py:38-61`). Requires the external `pdf2svg` binary on PATH.

```
→ pdf2svg 10240
← {"status": "continue"}
→ <10240 bytes of PDF>
← <binary frame: SVG file content>                (on success)
← {"status": "error", "error": ["Unable to convert file to SVG"]}   (pdf2svg exited non-zero)
```

Any exception is reported as `{"status": "error", "error": ["<str(e)>"]}`.

### `upload_to <file_size> <file_path>`

Upload a file and write it to `file_path` on the machine running fluxghost, creating parent directories as needed (`fluxghost/api/utils.py:77-95`).

```
→ upload_to 5000000 /tmp/foo/bar.bin
← {"status": "continue"}
→ <binary chunks...>
← {"status": "progress", "progress": 0.2}          (per chunk while incomplete; fraction 0–1)
← {"status": "ok"}
```

### `check_exist <file_path>`

`os.path.exists` check (`fluxghost/api/utils.py:63-67`).

```
→ check_exist /tmp/foo/bar.bin
← {"status": "ok", "res": true}
```

### `select_font <font_path>`

Copies the font file to `/usr/share/fonts/truetype/temp` and replies `{"status": "ok"}` (`fluxghost/api/utils.py:69-75`). If the path is not a file it first sends `{"status": "error", "error": ["NOT EXIST"]}` — but there is no `return` after `send_error`, so the copy is still attempted and raises an uncaught `FileNotFoundError`.

### `rgb_to_cmyk <file_size> <result_type>`

Upload an image; it is converted through the ICC profile `static/Coated_Fogra39L_VIGC_300.icc` (sRGB → CMYK, unless already CMYK; RGBA images are first composited onto white), then re-encoded as an RGB JPEG (quality 100, no subsampling) (`fluxghost/api/utils.py:97-129`). `result_type` is `base64` or anything else (Beam Studio sends `binary`).

```
→ rgb_to_cmyk 20480 binary
← {"status": "continue"}
→ <binary chunks...>
← {"status": "uploaded"}
← {"status": "complete", "length": 18345}
← <binary frame(s): JPEG bytes>
```

With `base64` the last two frames are replaced by `{"status": "ok", "data": "<base64 JPEG>"}`.

### `split_color <file_size> <color_type>`

Upload an image, get its four CMYK channels back as separate base64 JPEGs (`fluxghost/api/utils.py:131-173`). `color_type == 'cmyk'` uses PIL's plain `convert('CMYK')`; any other value (Beam Studio sends `rgb`) goes through the Fogra39 ICC transform. Each channel is inverted (`255 - x`) before encoding.

```
→ split_color 20480 rgb
← {"status": "continue"}
→ <binary chunks...>
← {"status": "uploaded"}
← {"status": "ok", "c": "<base64>", "m": "<base64>", "y": "<base64>", "k": "<base64>"}
```

### `get_similar_contours <file_size> [<is_spliced_img>]`

Upload an RGBA image (decoded via `COLOR_RGBA2BGRA`); finds groups of similar contours with `find_similar_contours` (`fluxghost/utils/contour/__init__.py:68`) and returns only the largest group (`fluxghost/api/utils.py:175-194`). `is_spliced_img` is `1` or `0` (default). Used by Beam Studio's Auto-Fit feature.

```
→ get_similar_contours 30000 0
← {"status": "continue"}
→ <binary chunks...>
← {"status": "ok", "data": [
     {"center": [120, 88], "angle": 0, "bbox": [80, 40, 80, 96]},
     {"center": [320, 90], "angle": 0.5236, "bbox": [280, 42, 80, 96]}
   ]}
```

Each element comes from `get_contour_info` (`fluxghost/utils/contour/contour_info.py:78-93`): `center` `[x, y]`, `angle` in radians relative to the group's first contour (first element is always `0`), `bbox` `[x, y, w, h]`. `data` is `[]` when no group of 2+ similar contours is found. This matches the frontend `AutoFit` interface (`packages/core/src/web/interfaces/IAutoFit.d.ts`).

### `get_all_similar_contours <file_size> [<is_spliced_img>]`

Same as above with `all_groups=True` (`fluxghost/api/utils.py:196-215`): `data` is an array of groups, each an array of contour infos that additionally include `"contour": [[x, y], ...]` (frontend type `AutoFitContour[][]`).

### `get_convex_hull <file_size>`

Upload an RGBA image; it is grayscaled, thresholded (`> 252` → background, inverted binary), external contours are combined and their convex hull computed (`fluxghost/api/utils.py:217-242`). The point list is rotated so the point nearest the origin comes first.

```
→ get_convex_hull 30000
← {"status": "continue"}
→ <binary chunks...>
← {"status": "ok", "data": [[12, 15], [200, 14], [210, 180], [11, 182]]}
```

`data` is `[]` when no contours are found.

## Errors

- Unknown command or bad numeric params (`ValueError`) → `{"status": "Error", "message": "BAD_PARAM_TYPE"}` — note the capitalized `Error` (`fluxghost/api/misc.py:50-52`).
- Text frame while a binary upload is pending → `{"status": "fatal", "symbol": ["PROTOCOL_ERROR"], "error": "PROTOCOL_ERROR"}` (`fluxghost/api/misc.py:48`).
- Binary frame with no upload pending → fatal `BAD_PROTOCOL`; more bytes than declared → fatal `BAD_LENGTH...` (`fluxghost/api/misc.py:17-27`, `86-89`).
- The three contour commands catch all exceptions and send `{"status": "error", "info": "<str(e)>"}` (no `error` array); the Beam Studio client rejects with `response.info`.
- `pdf2svg` failures use `send_error`, producing an `error` array as shown above.

## Example Session

```
→ check_exist /Applications
← {"status": "ok", "res": true}
→ get_similar_contours 152833 0
← {"status": "continue"}
→ <binary: 152833 bytes of PNG>
← {"status": "ok", "data": [{"center": [120, 88], "angle": 0, "bbox": [80, 40, 80, 96]}, ...]}
→ upload_to 3000000 /tmp/export/output.fc
← {"status": "continue"}
→ <binary: 1000000 bytes> → <binary: 1000000 bytes> → <binary: 1000000 bytes>
← {"status": "progress", "progress": 0.3333333333333333}
← {"status": "progress", "progress": 0.6666666666666666}
← {"status": "ok"}
```

## Notes

- Contour-command images are decoded with `cv2.COLOR_RGBA2BGRA` / `COLOR_RGBA2GRAY`, so the upload should be an image with an alpha channel (Beam Studio sends PNG blobs). Fully transparent areas are filled with the inverse of the average color before contour detection (`fluxghost/utils/contour/__init__.py:54-65`).
- `rgb_to_cmyk` and `split_color` send `{"status": "uploaded"}` immediately after the last binary chunk, before processing starts — the frontend only logs it.
- `utils-ws.ts` also defines an `upload(data, url)` method that sends `upload <url> <size>`, but the backend has no `upload` command in `cmd_mapping` (`fluxghost/api/utils.py:26-36`); it would get `{"status": "Error", "message": "BAD_PARAM_TYPE"}`. The matching backend command lives on `/ws/opencv`.
- Frontend consumers include Auto-Fit (`app/svgedit/operations/autoFit/`), color splitting (`helpers/layer/full-color/splitColor.ts`), framing (`helpers/device/framing.ts`), and font handling (`helpers/fonts/fontHelper.ts`).
