# Camera (live preview / monitoring)

`ws://127.0.0.1:<port>/ws/camera/<uuid>` or `ws://127.0.0.1:<port>/ws/camera/usb/<usb_addr>`

Streams JPEG frames from a connected machine's camera and accepts camera-control commands. For fisheye-camera models the backend can undistort and perspective-correct each frame before sending it to the client.

- **Handler**: [fluxghost/websocket/camera.py](../../fluxghost/websocket/camera.py) (`WebsocketCamera`) built from [fluxghost/api/camera.py](../../fluxghost/api/camera.py) (`camera_api_mixin`), which combines [fluxghost/api/fisheye_camera_mixin.py](../../fluxghost/api/fisheye_camera_mixin.py) and [fluxghost/api/control_base.py](../../fluxghost/api/control_base.py). Routes are registered in [fluxghost/http_websocket_route.py](../../fluxghost/http_websocket_route.py). - **Beam Studio client**: `packages/core/src/web/helpers/api/camera.ts` (class `Camera`).

## Connection

Two URL forms (see the route regexes in `http_websocket_route.py`):

- `/ws/camera/<uuid>` — `uuid` is a 32-hex-digit device UUID discovered over the network (`camera/(?P<uuid>[0-9a-fA-F]{32})`).
- `/ws/camera/usb/<usb_addr>` — `usb_addr` is a 1-3 digit USB (host-to-host) address (`camera/usb/(?P<usb_addr>[0-9]{1,3})`). Beam Studio picks this form when `device.source === 'h2h'`.

The **first text message must be the client's RSA key** (PEM). `control_base.py` loads it with `KeyObject.load_keyobj` and then tries to open the camera connection, emitting connection-stage messages:

```
← {"status": "connecting", "stage": "discover"}
← {"status": "connecting", "stage": "connecting"}
← {"status": "connected"}
```

For UUID targets the device must already be present in the discover cache, and `device.connect_camera(...)` is used (`get_robot_from_device` in `camera.py`, which also records `device.version` as `remote_version` and `device.model_id` as `remote_model`). For USB targets `FluxCamera.from_usb(...)` is used. On success the camera socket is added to the select loop (`CameraWrapper` in `camera.py`) and every frame the device pushes is forwarded to the websocket as a **binary JPEG** message.

Connection failures are sent as `status: "fatal"` and close the socket: `KEYOBJ_BAD_PARAMS` / `RSA_BAD_PARAMS` (bad key), `NOT_FOUND` (unknown UUID), `UNKNOWN_DEVICE` (unknown USB address), `PROTOCOL_ERROR` (USB open failed), `DISCONNECTED` (socket error), plus any robot error symbol (e.g. `REMOTE_IDENTIFY_ERROR`).

## Commands

All commands below are only handled when the device firmware version is greater than `1.0` (`remote_version > CRITICAL_VERSION` in `camera.py`); on older firmware every command is silently ignored and the endpoint is stream-only.

### `enable_streaming`

Calls `robot.enable_streaming()`. No JSON reply; frames then arrive continuously as binary messages.

### `require_frame` / `require_frame l`

Requests a single frame (`robot.require_frame()`). With the `l` argument, requests a low-resolution frame (`robot.require_frame(True)`) and flags the next incoming image as low resolution for fisheye processing. No JSON reply; the frame arrives as a binary message.

### `get_camera_count`

Sends the text command `camera_number` to the device and forwards the reply:

```
← {"status": "ok", "success": true, "data": "<raw device reply>"}
```

Beam Studio parses the count from the last `:`-separated token of `data`.

### `set_camera <idx>`

Sends `camera_change:<idx>` to the device. Reply has the same `{"status": "ok", "success": ..., "data": ...}` shape. (Matched with `cmd.startswith('set_camera')`.)

### `send_text <text>`

Raw text passthrough to the device (`robot.send_text`). Same reply shape as above. Beam Studio uses it for `get_exposure`, `set_exposure:<value>`, `get_exposure_auto`, `set_exposure_auto:<value>` and `get_camera_mode`.

### Fisheye parameter commands

Handled by `FisheyeCameraMixin.on_command` (reached via `super().on_command(...)`); unknown commands fall through it silently. All reply `{"status": "ok"}` on success or `{"status": "error", "error": ["Invalid version"]}` on version mismatch.

- `set_fisheye_matrix <json>` — camera calibration parameters. The `v` field selects the format:
  - `v` absent / `1` *(deprecated)*: `{k, d, points}` — per-height perspective points.
  - `v: 2`: `{v, k, d, refHeight, rvec_polyfit, tvec_polyfit, is_fisheye?}` — immediately computes perspective points for height 0 (equivalent to `set_fisheye_height 0`).
  - `v: 3`: `{v, k, d, rvec, tvec, is_fisheye?}` — requires a later `set_fisheye_grid` before frames can be transformed.
  - `v: 4`: `{v, k, d, rvec_polyfits, tvec_polyfits, grids, is_fisheye?, total_width?, total_height?}` — 9-region polyfits; immediately computes points for height 0.
  - Any other `v` → `{"status": "error", "error": ["Invalid version"]}`.
- `set_fisheye_height <h>` — recomputes perspective points for object height `h` (mm). Only valid for `v: 2` and `v: 4` params; otherwise replies `Invalid version` error. For `v: 2`, leveling data (if set) is subtracted per 3×3 region and the work area comes from `HW_PROFILE[model]` (fallback `430×320`).
- `set_fisheye_grid <json>` — `{"x": [start, end, step], "y": [start, end, step]}` (see `PerspectiveGrid` in Beam Studio's `FisheyePreview.d.ts`). Only valid for `v: 3` params.
- `set_leveling_data <json>` — 3×3 leveling offsets keyed `A`–`I`.
- `set_crop_param <json>` *(deprecated v1)* — `{width, height, cx, cy, top?, left?}`.
- `set_3d_rotation <json>` *(deprecated v1)* — `{rx, ry, rz, h, tx, ty}` (radians / mm). Also handled directly in `camera.py::on_command`.

## Binary frames

Every camera frame is sent to the client as one **binary websocket message containing a JPEG**. For the fisheye models `fad1`, `ado1`, `fbb2`, `fbm2`, `fhx2rf` (list in `camera.py`), if `set_fisheye_matrix` has been called, the frame is decoded, undistorted/perspective-transformed by `FisheyeCameraMixin.handle_fisheye_image` and re-encoded to JPEG first; otherwise the device's bytes are forwarded untouched. If decoding the fisheye frame fails, the raw bytes are forwarded as-is.

## Errors

- Connection-phase failures: `{"status": "fatal", "symbol": [...], "error": "<SYMBOL>"}` followed by socket close (see Connection above).
- `{"status": "error", "error": ["Invalid version"]}` — fisheye command with missing/incompatible `fisheye_param` version.
- On camera feed `RuntimeError` the websocket is closed by the server (`CameraWrapper.on_read`).
- Idle timeout: the base websocket closes the connection after 600 s without traffic (`WebSocketBase.TIMEOUT`).

## Example Session

```
→ -----BEGIN RSA PRIVATE KEY-----\n...          (rsaKey() from Beam Studio)
← {"status": "connecting", "stage": "discover"}
← {"status": "connecting", "stage": "connecting"}
← {"status": "connected"}
→ set_fisheye_matrix {"v": 2, "k": [[...]], "d": [[...]], "refHeight": 0, "rvec_polyfit": [...], "tvec_polyfit": [...]}
← {"status": "ok"}
→ set_fisheye_height 3.000
← {"status": "ok"}
→ require_frame l
← <binary JPEG frame>
→ get_camera_count
← {"status": "ok", "success": true, "data": "camera_number:2"}
→ enable_streaming
← <binary JPEG frame>
← <binary JPEG frame>
...
```

## Notes

- **Version gate**: `CRITICAL_VERSION = StrictVersion('1.0')` — every command requires `device.version > 1.0`. There is no error reply for older firmware; commands are dropped.
- **Fisheye model list vs. params**: fisheye processing needs both a model in `fisheye_models` *and* a prior `set_fisheye_matrix`; other models always get raw frames even if params were sent.
- **Low resolution frames**: `require_frame l` sets `is_next_image_low_resolution`, which makes `handle_fisheye_image` upscale-aware (pads via `pad_low_resolution_image` and divides the camera matrix by the computed downsample factor, `fisheye_camera_mixin.py`).
- **Frontend quirks** (`camera.ts`): Beam Studio retries `require_frame` up to 20 times at 500 ms intervals when a received blob is not a decodable image, and shows a "camera cable" alert after 10 retries. On non-Ador legacy models (`fbb1b`, `fbm1`, `fhexa1`, ...) it flips/crops the image client-side, and determines flipping by opening a *separate* `/ws/control/<uuid>` socket to run `config get camera_offset`.
- The docstring at the top of `websocket/camera.py` mentions `/ws/control/...`; it is a stale copy-paste — the real route is `/ws/camera/...`.
