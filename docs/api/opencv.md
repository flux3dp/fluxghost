# OpenCV

`ws://127.0.0.1:8000/ws/opencv`

General OpenCV image service. The client uploads an image once (keyed by its URL), then can request unsharp-mask sharpening of that cached image; the sharpened result is returned as a PNG binary frame. It also provides one-shot circular-blob detection (`detect_blobs`) used by Beam Studio's Print and Cut alignment, silhouette contours (`image_contour`) and the HEXA G galvo field-lens calibration solver (`solve_galvo_coupon`).

- **Handler**: `fluxghost/api/opencv.py` (`opencv_mixin`), wrapper `fluxghost/websocket/opencv.py`, route `fluxghost/http_websocket_route.py:29` - **Beam Studio client**: `packages/core/src/web/helpers/api/open-cv.ts` (`OpenCVWebSocket`, used by the Sharpen dialog `app/components/dialogs/image/Sharpen.tsx`)

## Connection

No URL parameters. Commands are plain-text frames `<cmd> <params...>` dispatched via `cmd_mapping` (`fluxghost/api/opencv.py:19-22`, `fluxghost/api/misc.py:29-56`). The connection holds per-session state: `self.imgs`, a dict mapping the client-supplied URL string to the decoded OpenCV image, plus an access-order history deque (`fluxghost/api/opencv.py:23-31`). State is lost when the socket closes.

## Commands

### `upload <img_url> <file_length>`

Uploads an image and caches it under `img_url` (`fluxghost/api/opencv.py:33-48`). `img_url` is an opaque key — the server never fetches it; the client sends the actual bytes. The image is decoded with PIL and converted `RGBA → BGRA` (`cv2.COLOR_RGBA2BGRA`), so it should have an alpha channel (Beam Studio uploads the blob fetched from an object URL).

```
→ upload blob:file:///1234-abcd 152833
← {"status": "continue"}
→ <binary chunks totalling 152833 bytes>
← {"status": "ok"}
```

Binary upload follows the standard `BinaryUploadHelper` flow (`fluxghost/api/misc.py:59-89`): stream binary frames until exactly `file_length` bytes have arrived.

### `sharpen <img_url> <sharpness> <radius>`

Applies an unsharp mask to the previously uploaded image (`fluxghost/api/opencv.py:50-65`). `sharpness` is parsed as float, `radius` as int. Implementation: Gaussian blur with kernel size `2 * radius + 1`, then `cv2.addWeighted(img, 1 + sharpness, blur, -sharpness, 0)`. The result is PNG-encoded and sent as a **single raw binary frame** with no preceding JSON header.

```
→ sharpen blob:file:///1234-abcd 3.5 2
← <binary frame: PNG bytes>
```

If `img_url` has not been uploaded on this connection:

```
→ sharpen blob:file:///1234-abcd 3.5 2
← {"status": "need_upload"}
```

The Beam Studio client reacts to `need_upload` by fetching the URL, running `upload`, and re-sending the same `sharpen` command (`open-cv.ts:82-112`).

### `detect_blobs <file_length> [<json_params>]`

Detects dark circular blobs (e.g. printed alignment marks) with `cv2.SimpleBlobDetector` (`find_blob_centers` in `fluxghost/utils/camera/corner_detection/find_corners.py`). Unlike `sharpen`, this is a one-shot command: the image is streamed directly after the command and is not cached in `self.imgs`.

`json_params` is an optional JSON object; recognized keys are forwarded to `find_blob_centers`: `min_threshold`, `max_threshold`, `min_area`, `max_area`, `min_circularity`, `max_circularity`, `min_convexity`, `max_convexity`. Unknown keys are ignored. The uploaded image is decoded with PIL, converted to RGB then BGR, so any common format (PNG/JPEG, with or without alpha) works.

Response `points` are blob centers in image pixel coordinates.

```
→ detect_blobs 152833 {"min_area": 500, "max_area": 3000, "min_circularity": 0.7}
← {"status": "continue"}
→ <binary chunks totalling 152833 bytes>
← {"status": "ok", "points": [[102.5, 88.1], [1893.2, 87.4], [103.0, 1401.8], [1894.1, 1400.2]]}
```

- **Beam Studio client**: `OpenCVWebSocket.detectBlobs` (`packages/core/src/web/helpers/api/open-cv.ts`), used by `app/components/dialogs/PrintAndCut/utils/alignByCamera.ts`.

### `image_contour <file_length> [<json_params>]`

Detects the outer silhouette of the image content and returns its contours — used by Beam Studio's Print and Cut, which builds the offset cut path client-side (round-join ClipperOffset on the raw silhouette). One-shot command like `detect_blobs`.

The mask comes from the alpha channel when the alpha channel actually contains background pixels (some `alpha == 0`; the mask is then `alpha > 0`, so anti-aliased thin strokes are kept). A merely translucent pixel — e.g. a resize artifact on the last row of an otherwise opaque PNG — does not switch to alpha mode; otherwise from luminance (`gray < threshold`, i.e. dark content on a light background), then `cv2.findContours(RETR_EXTERNAL)` + `approxPolyDP(epsilon)`. Contours smaller than `min_area` are dropped, where size is the filled pixel count (`contourArea + arcLength/2 + 1`, Pick's theorem) rather than the raw polygon area, so a 1 px-wide stroke of length ≥ `min_area` — e.g. a hairline along the image edge — is kept.

`json_params` keys (all optional): `threshold` (int, default 242, i.e. ~95% brightness), `epsilon` (float, default 1.0), `min_area` (float, default 100).

Response `contours` is a list of contours, each a list of `[x, y]` points in image pixel coordinates.

```
→ image_contour 152833 {"threshold": 250, "epsilon": 1.0}
← {"status": "continue"}
→ <binary chunks totalling 152833 bytes>
← {"status": "ok", "contours": [[[18.0, 42.0], [305.0, 12.0], ...]]}
```

- **Beam Studio client**: `OpenCVWebSocket.imageContour` (`packages/core/src/web/helpers/api/open-cv.ts`), used by `app/components/dialogs/PrintAndCut/utils/computeCutPathD.ts` (caches the contours per design, offsets them with ClipperOffset, and falls back to a bounding-box outline when this call fails).

### `solve_galvo_coupon <file_length> [<json_params>]`

Solves a HEXA G galvo field-lens calibration coupon: the galvo engraves a 9x9 node grid (plus discovery / validation / identity marks) on a dark sheet and the nozzle cuts 8 L marks around it as the ruler; Beam Studio captures the sheet with the head camera (`require_frame d20`, see camera.md), stitches a bed-coordinate image and sends it here. One-shot upload like `detect_blobs`. Implementation: `fluxghost/utils/camera/galvo_coupon.py` (`solve_galvo_coupon`), a port of the factory `correction.html` method; spec in beam-studio `docs/prd/hexa-ii-galvo/hexa-g-galvo-calibration.md` §7.2 (pattern), §7.8 (algorithm), §7.9 (outputs).

The image is decoded with PIL and converted to RGB (then BGR); PNG is expected (JPEG blurs the groove walls). Coordinates: image +x right, +y down; `expected_center_px` is where the galvo field centre C (= the nozzle position the L frame was cut around) lies in the image.

`json_params` (every key optional; defaults are the PRD §7.2 pattern):

| key | default | meaning |
|---|---|---|
| `px_per_mm` | 20 | nominal scale of the image; the real scale comes from the L frame |
| `pitch`, `grid` | 11, 9 | node spacing (mm) and nodes per side |
| `node_r`, `arm` | 1.25, [2.0, 4.5] | node ring radius and cross-arm extent (mm) |
| `discovery`, `validation` | 12 / 8 points | X-mark and validation-ring centres (command mm) |
| `identity`, `identity_r` | [-44, -51], 0.5 | identity ring centre and radius |
| `l_frame` | {"half": 70, "arm": 8} | L vertices on the square C +- half, arm length |
| `expected_center_px` | image centre | C in image px; may be off by several mm (the ruler is re-searched around its own origin) |
| `invert` | [true, true] | Beam Studio's `field.invertX/Y`; only the orientation prior when the identity ring is not found |
| `thresholds.galvo_green` | 150 | galvo marks = green channel > this (on a grayscale image: luminance) |
| `thresholds.l_frame` | [[200,"any"],[160,"red"],[120,"red"],[100,"any"],[60,"any"]] | tried in order: `[threshold, channel]`, channel `any` (luminance) / `red` / `green` / `blue`; channels other than `any` also exclude galvo-mask pixels (skipped on grayscale images). The first set whose ruler passes the self-check wins |
| `annotate` | false | also send a JPEG with the detections |

Algorithm (factory order; the "do not" items are measured failures on real scans): (1) masks — galvo marks by green channel, L frame by the threshold sequence restricted to a ring around C; (2) ruler — 6.5–11 mm connected components, two line fits per L and their intersection (groove geometric centre, not intensity centroid), vertices binned into the 3x3 nominal grid, least squares `px = A*mm + b`, one-at-a-time rejection of the worst vertex until residuals <= 0.5 mm with at least 6 kept, self-check: max vertex span within 2% of 197.99 mm and RMS < 0.5 mm; (3) nodes — rings by radial distribution (not hole filling), lattice from pairwise vectors grouped by direction (not length), orientation from the identity ring (which corner is (-44,-44) and which axis is Y), a conic (ellipse) fit per node; (4) affine `p = L c + t`, `L = R U` (QR, R rotation, U upper triangular with positive diagonal), `scale_x = U11`, `scale_y = sqrt(U12^2 + U22^2)`, `skew = atan2(U12, U22)`; (5) the 8 validation rings predicted by affine only and by affine + bilinear interpolation of the node residuals; (6) field centre = galvo origin in the L-frame coordinate system. Node coordinates are mapped to mm with the full `A^-1` (not only the two per-axis px/mm), so a rotated or anisotropic stitch does not leak into skew; the frame's own rotation is reported as `rotation_deg`.

Result (all mm unless noted; a quantity that could not be measured is `null`):

```
→ solve_galvo_coupon 1523311 {"px_per_mm": 20, "expected_center_px": [1800, 1800], "invert": [true, true], "annotate": true}
← {"status": "continue"}
→ <binary chunks totalling 1523311 bytes>
← {"status": "ok",
   "ruler": {"px_per_mm_x": 19.98, "px_per_mm_y": 20.01, "vertices_used": 8, "vertices_found": 8,
             "rms_mm": 0.07, "span_mm": 197.9, "threshold": [200, "any"]},
   "nodes_found": 81,
   "scale_x": 1.0203, "scale_y": 0.9798, "skew_deg": 0.31,
   "rotation_deg": 5.0, "mirrored": false,
   "affine_rms": 0.05, "affine_max": 0.12,
   "raw_rms": 0.82, "raw_max": 1.41,
   "validation_affine": {"rms": 0.04, "max": 0.07, "count": 8},
   "validation_bilinear": {"rms": 0.03, "max": 0.05, "count": 8},
   "field_center_mm": [3.2, -1.7],
   "orientation": {"source": "identity", "matches_invert": true, "identity_distance_mm": 0.03}}
← <binary frame: annotated JPEG>          (only with "annotate": true)
```

- `scale_x`, `scale_y`: actual mm / commanded mm (1.0 = correct); `skew_deg`: deviation of the axis angle from 90 deg.
- `affine_rms` / `affine_max`: `(p - Lc - t)` mapped back to galvo coordinates — the non-linear part. `raw_rms` / `raw_max`: `R^T (p - t) - c` — how far marks land from the commanded position, keeping scale and skew. The two are different quantities.
- `field_center_mm`: the galvo origin relative to C in the L-frame (nozzle) coordinate system, i.e. the measured "field centre relative to nozzle" (`toolhead_shift`).
- `rotation_deg`: galvo axes vs the L frame (extra, not in the factory output). `mirrored`: `det(L) < 0`; the Y axis is flipped before the decomposition so the scales stay positive.
- `orientation.source`: `identity` when the identity ring fixed the orientation, `invert` when the prior had to be used. `matches_invert` compares the two. Prior semantics (to be confirmed on the first real coupon): with `invert = [true, true]` (Beam Studio's CO2 default) command +X runs along image +x and +Y along image +y; a differing flag mirrors that axis.

Failure (no `ok`, no binary frame):

```
← {"status": "fail", "info": "RULER_INVALID", "reason": "200/any: only 4 L vertices found, need 6; ..."}
← {"status": "fail", "info": "GRID_INVALID", "reason": "only 3 ring candidates found"}
```

`RULER_INVALID` is the §7.8 self-check (fewer than 6 usable vertices, span or RMS out of range) for every threshold set; `GRID_INVALID` means no 9x9 lattice could be built or fewer than 6 nodes were measured. A failed ruler is "wrong", not "imprecise" — it is also the go/no-go for the camera capture path (PRD §7.6).

- **Tests**: `tests/usage/test_galvo_coupon.py` (synthetic coupon from `tests/usage/galvo_coupon_synth.py`, known affine recovered within 0.1 % / 0.02 deg; `RULER_INVALID` path) and `tools/ws_smoke.py` (`opencv.solve_galvo_coupon`).

## Errors

- Unknown command, or non-numeric `sharpness`/`radius`/`file_length`, or malformed `json_params` (`ValueError`) → `{"status": "Error", "message": "BAD_PARAM_TYPE"}` — capitalized `Error` (`fluxghost/api/misc.py:50-52`).
- Text frame during an active upload → `{"status": "fatal", "symbol": ["PROTOCOL_ERROR"], "error": "PROTOCOL_ERROR"}` (`fluxghost/api/misc.py:48`).
- Binary frame with no upload in progress → fatal `BAD_PROTOCOL`; more bytes than declared → fatal `BAD_LENGTH...` (`fluxghost/api/misc.py:17-27`, `86-89`).
- `sharpen` on an unknown key is not an error — it returns `{"status": "need_upload"}` as shown above.
- There is no try/except around image decoding or sharpening; a corrupt upload raises an uncaught exception in the handler instead of producing an error frame.

## Example Session

```
→ sharpen blob:file:///1234-abcd 3.5 2
← {"status": "need_upload"}
→ upload blob:file:///1234-abcd 152833
← {"status": "continue"}
→ <binary: 152833 bytes of PNG>
← {"status": "ok"}
→ sharpen blob:file:///1234-abcd 3.5 2
← <binary frame: sharpened PNG>
→ sharpen blob:file:///1234-abcd 5.0 4
← <binary frame: sharpened PNG>
```

## Notes

- Because the source image stays cached, the Sharpen dialog can re-run `sharpen` with different parameters cheaply after the first upload.
- `update_history` (`fluxghost/api/opencv.py:26-31`) keeps a most-recently-used deque capped at 5 entries, but only the deque is trimmed — evicted URLs are **not** deleted from `self.imgs`, so decoded images accumulate for the lifetime of the connection.
- `sharpness` and `radius` are not range-checked. `radius` values ≥ 0 yield valid odd kernel sizes; the client UI is responsible for sensible bounds.
- The binary response is a bare `send_binary` (`fluxghost/api/opencv.py:65`) — unlike `ApiBase.send_binary_buffer` there is no `{"status": "binary", ...}` preamble. The frontend simply resolves the first Blob it receives.
