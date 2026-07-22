# Camera Calibration

`ws://127.0.0.1:<port>/ws/camera-calibration`

Stateless-per-session image-processing endpoint used by Beam Studio's camera calibration wizards: chessboard/charuco detection, intrinsic (k/d) calibration, extrinsic solvePnP refinement, and preview remapping. It never talks to a device — all images are uploaded by the client.

- **Handler**: [fluxghost/websocket/camera_calibration.py](../../fluxghost/websocket/camera_calibration.py) (`WebsocketCameraCalibration`) built from [fluxghost/api/camera_calibration.py](../../fluxghost/api/camera_calibration.py) (`camera_calibration_api_mixin`); command dispatch and uploads via `OnTextMessageMixin` / `BinaryUploadHelper` in [fluxghost/api/misc.py](../../fluxghost/api/misc.py); math in [fluxghost/utils/camera/](../../fluxghost/utils/camera/). - **Beam Studio client**: `packages/core/src/web/helpers/api/camera-calibration.ts` (class `CameraCalibrationApi`).

## Connection

No URL parameters and no authentication (route regex `camera-calibration` in [fluxghost/http_websocket_route.py](../../fluxghost/http_websocket_route.py)). Nothing is sent on open; the socket immediately accepts commands. The handler keeps two pieces of session state:

- `calibration_params` — dict of `k`, `d`, `rvec`, `tvec`, `rvec_polyfit`, `tvec_polyfit`, `levelingData`, `is_fisheye`, filled by `calibrate_camera` / `calibrate_chessboard` / `solve_pnp_calculate` / `update_data` and consumed by the `solve_pnp_*` and `remap_image` commands.
- Fisheye multi-image state (`fisheye_calibrate_imgs`, `fisheye_calibrate_heights`, `interrupted`) reset by `start_fisheye_calibration`.

**Binary upload protocol** (used by every command that takes an image): the client sends `command <file_length> ...`, the server replies `{"status": "continue"}`, the client then sends the image bytes (JPEG/PNG, any PIL-decodable format) as one or more binary messages totalling exactly `file_length` bytes, and the server runs the command's callback on the assembled buffer.

## Commands

### `upload <file_length>`

Legacy (pre-fisheye) calibration-picture analysis. After the binary upload, finds the four main Hough lines of the engraved calibration square (`calc_picture_shape`).

- `← {"status": "continue"}` then, after upload:
- `← {"status": "ok", "x": <float>, "y": <float>, "angle": <radians>, "width": <float>, "height": <float>}` — center, rotation and size in pixels
- `← {"status": "none"}` — no lines found
- `← {"status": "fail"}` — HoughLines returned NaN

### `start_fisheye_calibration`

Resets the multi-image fisheye state (including the `interrupted` flag). `← {"status": "ok"}`

### `add_fisheye_calibration_image <file_length> <height>`

Queues one chessboard photo taken at object height `<height>` (mm, float) for `do_fisheye_calibration`. `← {"status": "continue"}` → binary upload → `← {"status": "ok"}`

### `do_fisheye_calibration`

Runs `calibrate_fisheye_camera` (from [fluxghost/utils/camera/calibration.py](../../fluxghost/utils/camera/calibration.py)) over all queued images with the 48×36 `CHESSBOARD` pattern. Emits progress while detecting corners:

```
← {"status": "progress", "progress": <float 0..1>}
...
← {"status": "ok", "ret": <float>, "k": [[...]], "d": [[...]], "rvec": [...], "tvec": [...],
   "rvec_polyfit": [[...]], "tvec_polyfit": [[...]]}
```

`tvec`s are shifted by `(35, 55, 0)` (chessboard origin → laser origin) before a degree-1 polyfit of rvec/tvec against the image heights; `rvec`/`tvec` in the reply are the polyfit evaluated at height 0. On error: `{"status": "fail", "reason": "<exception>"}` (suppressed entirely if `interrupt` was received).

### `calibrate_chessboard <file_length> <height> <chess_w> <chess_h>`

Single-image chessboard calibration (used e.g. for BB2). `← {"status": "continue"}` → binary upload, then the server calibrates with the `<chess_w>×<chess_h>` pattern at `<height>`, stores `k`/`d`/`rvec`/`tvec` into `calibration_params` (tvec offset `(35, 55, 0)` applied) and replies:

```
← <binary JPEG: remapped image annotated with detected (red) and projected (blue) corners>
← {"status": "ok", "ret": <float>, "k": [[...]], "d": [[...]], "rvec": [[...]], "tvec": [[...]]}
```

On failure: `{"status": "fail", "reason": "<exception>"}`. Note the binary frame is sent *before* the `ok` JSON; the frontend caches the blob and resolves on `ok`.

### `detect_charuco <file_length> <squares_x> <squares_y> [<opts_json>]`

Detects a ChArUco board (`get_calibration_data_from_charuco` in [fluxghost/utils/camera/charuco/detect.py](../../fluxghost/utils/camera/charuco/detect.py)). `opts_json` currently supports `{"is_vertical": <bool>}` (default `false`); a malformed `opts_json` is ignored with defaults. `← {"status": "continue"}` → binary upload →

```
← {"status": "ok", "imgp": [[x, y], ...], "objp": [[x, y, z], ...], "ratio": <found ratio>}
```

or `{"status": "fail", "reason": "Failed to detect image."}`.

### `calibrate_camera <objpoints_json> <imgpoints_json> <img_size_json> [<is_fisheye>]`

Intrinsic calibration from point correspondences (typically the output of one or more `detect_charuco` calls). `objpoints_json` / `imgpoints_json` are arrays of per-image point arrays; `img_size_json` is `[w, h]`; `<is_fisheye>` is the literal `true`/`false` (default `true` when omitted). When fisheye, image points are shifted by the fixed padding `(L_PAD, T_PAD) = (1168, 876)` and the size is padded accordingly ([fluxghost/utils/camera/constants.py](../../fluxghost/utils/camera/constants.py)). Results are stored into `calibration_params`.

```
← {"status": "ok", "ret": <float>, "k": [[...]], "d": [[...]], "rvec": [[...]], "tvec": [[...]],
   "indices": [<kept image indices>], "is_fisheye": <bool>}
```

On failure: `{"status": "fail", "reason": "<exception>"}`. `indices` lists which input images survived outlier rejection in `calibrate_camera` (utils).

### `calibrate_fisheye <objpoints_json> <imgpoints_json> <img_size_json>`

**Deprecated** alias for `calibrate_camera` (logs a warning and forwards). Beam Studio still sends this form when `isFisheye` is true (`camera-calibration.ts::calibrateCamera`).

### `update_data <json>`

Injects previously saved calibration data into `calibration_params` without recalibrating. Recognized keys: `k`, `d`, `rvec`, `tvec`, `rvec_polyfit`, `tvec_polyfit`, `levelingData` (converted to numpy arrays) and `is_fisheye`. `← {"status": "ok"}`

### `remap_image <args_json>`

`args_json` = `{"size": <file_length>, "params": {"k": ..., "d": ..., "is_fisheye": ...}?}`. Missing `params` entries fall back to the stored `calibration_params` (`is_fisheye` defaults `true`). If no `k`/`d` are available: `{"status": "fail", "info": "NO_DATA", "reason": "No calibration data found"}`. Otherwise `← {"status": "continue"}` → binary upload → `← <binary JPEG: lens-undistorted image>` (padded first when fisheye). No `ok` JSON follows.

### `solve_pnp_find_corners <ref_points_json> <dh> <file_length> [<interest_area_json>]`

Step 1 of extrinsic refinement. Requires stored `k`/`d`/`rvec`/`tvec` (else `{"status": "fail", "info": "NO_DATA", "reason": "No calibration data found"}`). `ref_points_json` is `[[x, y], ...]` in mm (mapped to 3-D as `(x, y, -dh)`), `dh` the height offset (rounded to 2 decimals), `interest_area_json` an optional `{"x", "y", "width", "height"}` crop in image pixels.

`← {"status": "continue"}` → binary upload. The image is remapped, blob centers are detected (`find_blob_centers`) and matched against the projected reference points with a KD-tree scoring pass (soft-inlier score, sigma 30 px; a total score ≥ 0.5 is required, per-point scores < 0.3 are replaced by reference offsets). If matching fails, the projected points themselves (optionally recentered on the interest area) are returned; with an interest area, results are clamped to its inner 90%.

```
← {"status": "ok", "points": [[x, y], ...]}
← <binary JPEG: the remapped image, for the user to verify/adjust the points on>
```

### `solve_pnp_calculate <ref_points_json> <dh> <img_points_json>`

Step 2: computes new extrinsics from the (possibly user-corrected) image points. Distorts the points back and runs `solve_pnp` ([fluxghost/utils/camera/solve_pnp.py](../../fluxghost/utils/camera/solve_pnp.py)). Stores `rvec`/`tvec` into `calibration_params`.

```
← {"status": "ok", "rvec": [[...]], "tvec": [[...]]}
```

Failures: `{"status": "fail", "reason": "solve pnp failed"}` (solver returned false) or `{"status": "fail", "reason": "solve pnp failed<exception>"}`.

### `check_pnp <args_json>`

Verification render. `args_json` = `{"size": <file_length>, "dh": <float>, "grid": {"x": [start, end, step], "y": [start, end, step]}, "params": {"k", "d", "is_fisheye"?, ...}}` where `params` additionally carries either `rvec`/`tvec` (single extrinsic) or `rvecs`/`tvecs` (per-region dicts for wide-angle V4, keys like `topLeft` ... `bottomRight`, see `calculate_regional_perspective_points` in [fluxghost/utils/camera/perspective.py](../../fluxghost/utils/camera/perspective.py)). `← {"status": "continue"}` → binary upload → `← <binary JPEG: perspective-corrected image>`. If neither extrinsic form is present: `{"status": "fail", "reason": "No pnp provided"}`. No `ok` JSON follows the image.

### `extrinsic_regression <rvecs_json> <tvecs_json> <heights_json>`

Degree-1 polyfit of rvec/tvec lists against heights (for V2/V4 parameter generation):

```
← {"status": "ok", "rvec_polyfit": [[...]], "tvec_polyfit": [[...]]}
```

### `interrupt`

Sets the `interrupted` flag and replies `{"status": "ok"}`. The flag only suppresses the response of an in-flight `do_fisheye_calibration` / `calibrate_chessboard` (checked after computation or on exception); it is cleared by `start_fisheye_calibration`.

## Errors

- Unknown command → `{"status": "Error", "message": "BAD_PARAM_TYPE"}` (capital `E`; from `OnTextMessageMixin`).
- Text message while a binary upload is pending → `{"status": "fatal", ...}` with symbol `PROTOCOL_ERROR` and socket close.
- Binary message with no upload pending → fatal `BAD_PROTOCOL`.
- More bytes than declared `file_length` → fatal `BAD_LENGTH ...`.
- Upload stalled > 60 s → fatal `TIMEOUT` / `WAITING_BINARY` (`check_ttl` in [fluxghost/websocket/base.py](../../fluxghost/websocket/base.py)).
- Per-command failures use `{"status": "fail", "reason": ...}` and, where noted, `"info": "NO_DATA"`.

## Example Session

A fixed-focus (V3-style) charuco calibration followed by solvePnP refinement:

```
→ detect_charuco 152340 15 10 {}
← {"status": "continue"}
→ <binary: photo bytes>
← {"status": "ok", "imgp": [[512.3, 302.1], ...], "objp": [[0, 0, 0], ...], "ratio": 0.93}
→ calibrate_camera [[[0,0,0],...]] [[[512.3,302.1],...]] [3264,2448]
← {"status": "ok", "ret": 0.42, "k": [[...]], "d": [[...]], "rvec": [[...]], "tvec": [[...]],
   "indices": [0], "is_fisheye": true}
→ solve_pnp_find_corners [[-60,10],[60,10],[-60,90],[60,90]] 0.000 148211
← {"status": "continue"}
→ <binary: photo bytes>
← {"status": "ok", "points": [[1023.5, 771.2], ...]}
← <binary JPEG: remapped image>
→ solve_pnp_calculate [[-60,10],[60,10],[-60,90],[60,90]] 0.000 [[1023.5,771.2],...]
← {"status": "ok", "rvec": [[...]], "tvec": [[...]]}
→ check_pnp {"size": 148211, "dh": 0, "grid": {"x": [0, 430, 10], "y": [0, 320, 10]}, "params": {"k": [[...]], "d": [[...]], "rvec": [[...]], "tvec": [[...]]}}
← {"status": "continue"}
→ <binary: photo bytes>
← <binary JPEG: perspective-corrected image>
```

## Notes

- **Chessboard vs charuco vs blob flows**: Ador-era calibration uses the multi-height chessboard flow (`start_fisheye_calibration` → `add_fisheye_calibration_image` × N → `do_fisheye_calibration`, fixed 48×36 board); newer flows use `detect_charuco` + `calibrate_camera` for intrinsics and `solve_pnp_find_corners`/`solve_pnp_calculate` (red laser-dot blobs) for extrinsics.
- **Fisheye padding**: fisheye images are padded by the fixed constants `T_PAD/B_PAD = 876`, `L_PAD/R_PAD = 1168` around the nominal `3264×2448` sensor image before remapping (`constants.py`, `pad_image` in `general.py`). `calibrate_camera` applies the same offsets to input image points — clients pass *unpadded* coordinates.
- **Laser-origin offset**: both `do_fisheye_calibration` and `calibrate_chessboard` add `(35, 55, 0)` mm to tvec to move the origin from the chessboard corner to the laser origin. `calibrate_camera` (charuco path) does not.
- **Known quirk**: `cmd_solve_pnp_calculate` does not `return` after sending the `NO_DATA` fail message, so calling it before any calibration data exists additionally raises a `KeyError` server-side (`camera_calibration.py` line 417-420).
- **Debug output**: when fluxghost runs with debug-image writing enabled (`WRITE_DEBUG_IMG` in `fluxghost/debug.py`), the solve-pnp and check-pnp steps dump annotated PNGs (`solve-pnp-input.png`, `solve-pnp-corner.png`, `check_pnp.png`).
- **Frontend quirks** (`camera-calibration.ts`): the client keeps a single module-level socket (`cameraCalibrationApi`), still sends the deprecated `calibrate_fisheye` for fisheye lenses, and sends `dh` with `toFixed(2)`/`toFixed(3)` while the server re-rounds to 2 decimals.
