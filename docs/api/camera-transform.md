# Camera Transform

`ws://127.0.0.1:<port>/ws/camera-transform`

Applies fisheye undistortion + perspective correction to client-uploaded images, using the same `FisheyeCameraMixin` pipeline as the live camera endpoint — but without any device connection. Beam Studio uses it to re-transform previously captured photos (e.g. when re-rendering saved preview images).

- **Handler**: [fluxghost/websocket/camera_transform.py](../../fluxghost/websocket/camera_transform.py) (`WebsocketCameraTransform`) built from [fluxghost/api/camera_transform.py](../../fluxghost/api/camera_transform.py) (`camera_transform_api_mixin`), combining [fluxghost/api/fisheye_camera_mixin.py](../../fluxghost/api/fisheye_camera_mixin.py), `OnTextMessageMixin` and `BinaryHelperMixin` from [fluxghost/api/misc.py](../../fluxghost/api/misc.py). - **Beam Studio client**: `packages/core/src/web/helpers/api/camera-transform.ts` (class `CameraTransformAPI`).

## Connection

No URL parameters and no authentication (route regex `camera-transform` in [fluxghost/http_websocket_route.py](../../fluxghost/http_websocket_route.py)). Nothing is sent on open. Session state is the fisheye parameter set (`fisheye_param`), initially `None`.

Command dispatch goes through `OnTextMessageMixin.on_text_message` using `cmd_mapping`, which contains exactly four commands: the three registered by `FisheyeCameraMixin.__init__` (`set_fisheye_matrix`, `set_leveling_data`, `set_fisheye_grid`) plus `transform_image`. `FisheyeCameraMixin.on_command` is **not** wired up on this endpoint, so `set_fisheye_height`, `set_crop_param` and `set_3d_rotation` are *not* available here (they would produce the unknown-command error below).

## Commands

### `set_fisheye_matrix <json>`

Sets the calibration parameters used by `transform_image`. The `v` field selects the format (see `set_fisheye_matrix` in [fluxghost/api/fisheye_camera_mixin.py](../../fluxghost/api/fisheye_camera_mixin.py)):

- `v` absent / `1` *(deprecated)*: `{"k", "d", "points"}`.
- `v: 2`: `{"v": 2, "k", "d", "refHeight", "rvec_polyfit", "tvec_polyfit", "is_fisheye"?}` — perspective points are immediately computed for height 0. Since this endpoint has no connected device, the work-area lookup falls back to `{"width": 430, "length": 320}` (`HW_PROFILE.get(None, ...)`).
- `v: 3`: `{"v": 3, "k", "d", "rvec", "tvec", "is_fisheye"?}` — a follow-up `set_fisheye_grid` is required before `transform_image` can produce a corrected image.
- `v: 4`: `{"v": 4, "k", "d", "rvec_polyfits", "tvec_polyfits", "grids", "is_fisheye"?, "total_width"?, "total_height"?}` — perspective points computed for height 0.

`← {"status": "ok"}` on success; `← {"status": "error", "error": ["Invalid version"]}` for an unrecognized `v`.

### `set_fisheye_grid <json>`

`{"x": [start, end, step], "y": [start, end, step]}` (mm; `PerspectiveGrid` in Beam Studio's `FisheyePreview.d.ts`). Projects the grid with the stored `rvec`/`tvec` and stores the perspective points. Only valid when the current `fisheye_param` has `v: 3`; otherwise `← {"status": "error", "error": ["Invalid version"]}`. On success `← {"status": "ok"}`.

### `set_leveling_data <json>`

Stores 3×3 leveling offsets keyed `A`–`I`. `← {"status": "ok"}`. (Only consumed when perspective points are recomputed, which on this endpoint happens inside `set_fisheye_matrix` for `v: 2`.)

### `transform_image <file_length>`

Uploads an image and receives the transformed result:

```
→ transform_image 234567
← {"status": "continue"}
→ <binary: image bytes, exactly 234567 bytes total>
← <binary JPEG: undistorted + perspective-corrected image>
```

The uploaded buffer is decoded with PIL, converted to BGR, run through `FisheyeCameraMixin.handle_fisheye_image` (pad → `get_remap_img(k, d)` → `apply_points` perspective warp) and re-encoded as JPEG. No `ok` JSON follows the binary reply.

If `fisheye_param` is `None` (no `set_fisheye_matrix` yet) — or decoding to OpenCV fails — the code calls `self.send_binary(image)` with the *PIL Image object* rather than the original bytes ([fluxghost/api/camera_transform.py](../../fluxghost/api/camera_transform.py) lines 37-45), which is not a valid binary payload; in practice Beam Studio always sets parameters before uploading.

## Errors

- Unknown command → `{"status": "Error", "message": "BAD_PARAM_TYPE"}` (from `OnTextMessageMixin`).
- Text message while a binary upload is pending → fatal `PROTOCOL_ERROR` and socket close.
- Binary data with no upload pending → fatal `BAD_PROTOCOL`.
- More bytes than the declared `file_length` → fatal `BAD_LENGTH ...`.
- Upload stalled > 60 s → fatal `TIMEOUT` / `WAITING_BINARY`.
- `{"status": "error", "error": ["Invalid version"]}` — `set_fisheye_matrix` with bad `v`, or `set_fisheye_grid` when params are not `v: 3`.

## Example Session

A BB2-style (v3, fixed focus) transform:

```
→ set_fisheye_matrix {"v": 3, "k": [[...]], "d": [[...]], "rvec": [[...]], "tvec": [[...]]}
← {"status": "ok"}
→ set_fisheye_grid {"x": [0, 600, 10], "y": [0, 375, 10]}
← {"status": "ok"}
→ transform_image 234567
← {"status": "continue"}
→ <binary: JPEG bytes>
← <binary JPEG: corrected image>
```

## Notes

- **Height is fixed at 0** for v2/v4 parameters: `set_fisheye_matrix` internally calls `set_fisheye_height(0, None)` and there is no reachable command to change the height on this endpoint (unlike `/ws/camera`, where `set_fisheye_height` works via `on_command`).
- **v1 params behave differently**: with `v: 1` matrices, `handle_fisheye_image` uses the per-height `points` grid and the deprecated crop/3-D-rotation path — but since `set_crop_param`/`set_3d_rotation` are unreachable here, v1 images are transformed without cropping.
- **is_fisheye flag**: every parameter version accepts `"is_fisheye"` (default `true`); when `false`, standard (non-fisheye) undistortion is used and the pre-remap padding step is skipped (`handle_fisheye_image` in `fisheye_camera_mixin.py`).
- **Frontend quirks** (`camera-transform.ts`): the client rounds all numbers in the parameter JSON to 6 decimal places before sending, exposes only `setFisheyeParam` (→ `set_fisheye_matrix`), `setFisheyeGrid` and `transformImage`, and treats any non-`ok` JSON reply as a soft failure (`resolve(false)`).
