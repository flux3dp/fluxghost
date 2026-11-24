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

`← {"status": "continue"}` → binary upload. The image is remapped, blob centers are detected (`find_blob_centers`) and matched against the projected reference points by `match_projected_points` ([fluxghost/utils/camera/corner_detection/match_points.py](../../fluxghost/utils/camera/corner_detection/match_points.py)). Each (anchor point, candidate corner) hypothesis is scored **relative** (KD-tree soft-inlier score of the pattern translated onto the candidate, sigma 60 px) **+ absolute** (agreement between that translation and the projected pose, sigma 300 px); ranking uses the sum, acceptance uses the relative score alone (≥ 0.5), so a stale `rvec`/`tvec` can only break ties, never reject a clear match. Per-point scores < 0.1 are replaced by anchor + reference offset. If matching fails, the projected points themselves (optionally recentered on the interest area) are returned; with an interest area, results are clamped to its inner 90%.

```
← {"status": "ok", "points": [[x, y], ...]}
← <binary JPEG: the remapped image, for the user to verify/adjust the points on>
```

### `solve_pnp_calculate <ref_points_json> <dh> <img_points_json>`

Step 2: computes new extrinsics from the (possibly user-corrected) image points. Distorts the points back and runs `solve_pnp` ([fluxghost/utils/camera/solve_pnp.py](../../fluxghost/utils/camera/solve_pnp.py)). Stores `rvec`/`tvec` into `calibration_params`.

```
← {"status": "ok", "rvec": [[...]], "tvec": [[...]]}
```

`rms` is the reprojection error in remapped-image px (root mean square of the per-point distance).

Failures: `{"status": "fail", "info": "NO_DATA", "reason": "No calibration data found"}` (no stored `k`), `{"status": "fail", "reason": "solve pnp failed"}` (solver returned false) or `{"status": "fail", "reason": "solve pnp failed<exception>"}`.

### `auto_pnp_detect <file_length>`

Automatic alternative to `solve_pnp_find_corners`, step 1: find the engraved marks in one photo. Requires stored `k`/`d` (else the `NO_DATA` failure above); no `rvec`/`tvec` and no interest area. `← {"status": "continue"}` → binary upload of the raw camera photo.

Dark blobs are detected on the raw frame (`detect_marks`, [fluxghost/utils/camera/auto_pnp.py](../../fluxghost/utils/camera/auto_pnp.py), same detector parameters as `find_blob_centers`) and only their centres are undistorted, so `x`, `y` are in the same remapped-image px space as `solve_pnp_find_corners` returns and `solve_pnp_calculate` takes. The camera model follows the stored `is_fisheye` (`update_data`, default fisheye): a fisheye photo is padded and undistorted with `cv2.fisheye`, a pinhole one (fhx2rf wide-angle) is not padded and is undistorted with `cv2.undistortPointsIter`, iterated to convergence where `cv2.undistortPoints` stops after 5 steps (since 2.5.9). `contrast` is the brightness of a ring around the blob minus the blob.

```
← {"status": "ok", "blobs": [[x, y, size, contrast], ...], "weak": [[x, y, size, contrast], ...]}
```

`blobs` holds the marks plus stray blobs (chassis, text). `weak` is a second detection with the minimum area lowered from 15 px to 4 px (`WEAK_MIN_AREA`), everything else equal: it catches marks that lens flare or a faint engraving leaves below the normal detector, among hundreds of noise blobs. Call it once per exposure; telling marks from strays is `auto_pnp_match`'s job.

### `auto_pnp_match <args_json>`

Step 2: tell which blob is which mark. `args_json` = `{"ref_points": [[x, y], ...], "blobs": [[[x, y, size, contrast], ...], ...], "weak": [[[x, y, size, contrast], ...], ...], "r_max": <mm>}` (`r_max` optional, the `HIGH_RESIDUAL` limit, default `R_MAX_MM`; callers with 8 marks pass a tighter one, since a homography through 8 points absorbs most of one wrong mark): `ref_points` are the mark positions in mm in any order, either a full rectangular lattice (fbm2, wide-angle: 4 x 4) or nested rectangles (laser head, Ador: 8 marks); `blobs` and the optional `weak` hold one `auto_pnp_detect` result per exposure. Stateless, needs no stored data.

Blobs from different exposures within 8 px are one mark, kept from the exposure with the best contrast. `match_grid` then fits one homography between the bed plane and the blob centres with no pose prior: every cell (a mark, the next mark to its right, the next one below and the one closing the rectangle: the lattice cells, or each of the nested rectangles) seeded from a blob and its right, lower and diagonal neighbours, grown by assigning each grid position its nearest blob within 15 mm on the bed (`ASSIGN_TOL_MM`), then settled at 3 mm (`TIGHT_TOL_MM`), starting from a RANSAC fit of the loose assignment, so a stray near a covered mark is dropped instead of taking its place. For a layout that is not a full lattice the seed may be any blobs, not only neighbouring ones. It assumes only that bed +x / +y run along image +x / +y.

When at least 7 in 8 of the marks matched (`FILL_MIN_FRACTION`: 14 of 16, 7 of 8), `fill_missing` predicts each missing mark from that homography and takes the median of the `weak` blobs within 2 mm of it (`FILL_TOL_MM`). `weak` blobs are never used for the matching itself.

```
← {"status": "ok", "points": [[x, y], ...], "matched": <n>, "filled": <n>, "rms": <mm>}
← {"status": "fail", "reason": "NOT_ENOUGH_MARKS" | "HIGH_RESIDUAL", "points": [[x, y] | null, ...], "matched": <n>, "filled": <n>, "rms": <mm | null>}
```

`points` is ordered like `ref_points` and feeds `solve_pnp_calculate` directly. A fail carries them too, with `null` for a mark that was not found: after `HIGH_RESIDUAL` all of them are there and the caller may offer to continue with them. `matched` counts every mark found, `filled` how many of them came from `weak`. `rms` is the residual of the matched marks to the homography, in bed mm. `NOT_ENOUGH_MARKS`: fewer blobs matched than `ref_points` (every mark is required). `HIGH_RESIDUAL`: all matched but `rms` > `R_MAX_MM` (1.0), which means a stray took a mark's place or `k`/`d` describe this camera poorly.

#### auto_pnp constants

The values in `fluxghost/utils/camera/auto_pnp.py` and what each one rests on. Measurements are from office units: three `fbm2`, one `fbb2`, one `fhx2rf`, one `ado1`. The photos behind them are the fixtures of `tests/usage/test_auto_pnp.py`.

| Constant | Value | Basis |
|---|---|---|
| `SAME_MARK_PX` | 8 px | One mark moves by less than 1 px between exposures (0.4 px on `fbm2`, 0.6 px on `fbb2`); the closest two marks of any layout are more than 100 px apart. |
| `ASSIGN_TOL_MM` | 15 mm | Loose on purpose: a fit seeded from one cell extrapolates badly across the bed. |
| `TIGHT_TOL_MM` | 3 mm | Correct marks sit within about 1 mm of the settled fit. Seen on `fbm2`: a board over two marks carried a blob 7 mm from one of them, which was assigned at 15 mm and dragged the fit. With 8 marks a stray 14 mm from a missing mark cost a real mark its place, hence the RANSAC start of the tight stage. |
| `R_MAX_MM` | 1.0 mm | Every mark is required (each `fbm2` region pose is solved from exactly its four marks), so this is the only quality gate left. With all 16 marks matched the residual was 0.38 to 0.71 mm, and the worst preview error inside the mark grid is about the same figure, so 1.0 aims at a preview within about 1 mm. A stray taking a mark's place on the 16-mark lattice gives 3 mm or more. |
| `r_max` passed for 8 marks | 0.2 mm (Beam Studio) | A homography through 8 points absorbs most of one wrong mark. Correct matches: 0.04 to 0.05 mm (`fbb2`, `ado1`), 0.10 mm (`fhx2rf`). One mark displaced by 1 / 2 / 3 mm: 0.15 to 0.31 / 0.31 to 0.62 / 0.47 to 0.93 mm (simulated on an `fbb2` photo). Seen on `ado1`: an old mark 4 mm from a hidden one gave 0.72 mm. |
| `WEAK_MIN_AREA`, `FILL_TOL_MM` | 4 px, 2 mm | Seen on one `fbm2`: lens flare from the light panel left two corner marks at a tenth of the usual contrast, below what the detector picks out of a whole photo at any exposure, yet visible where the other 14 put them. A weak detection returns hundreds of blobs per photo, mostly paper texture; a random position on paper has one within 2 mm in about 2 % of cases (seven exposures). |
| `FILL_MIN_FRACTION` | 0.875 (14 of 16, 7 of 8) | With two of the 8 nested-rectangle marks missing, a homography that squeezes the pattern along a diagonal fits six real marks to wrong positions with no residual (an `ado1` photo), and the fill would then look in the wrong place. |
| `SEED_ASPECT` | 2.5 | Only prunes seeds. Perspective on the `fbm2` camera changes a cell's width / height ratio by up to about 1.3. |
| `MAX_ANISOTROPY` | 1.25 | Seen on `ado1`: an old `fbb2` laser-head pattern on a reused sheet (120 × 80 mm, inner 60 × 40) was taken for the Ador one (120 × 120, inner 60 × 60) with 0.05 mm of residual, and the preview at that height was wrong; its ratio of x scale to y scale is 1.5. True matches of the nested-rectangle layouts: 0.94 to 1.03 (`fbb2` straight, the oblique default points, `fhx2rf`, `ado1`). Not applied to lattices: a lid camera looks at the bed obliquely and a real lattice can be stretched more than that. |

Matching time: nothing measurable when all marks are found (the first complete, well-fitting hypothesis returns). With marks missing every seed is tried: 1 to 2 s at 40 blobs, 6 to 9 s at 75 to 95 blobs (`fbm2`, seven exposures merged). For the nested-rectangle layouts a seed must also explain half of the other marks before it is refined, which took a 54-blob failing photo from 41 s to 2 s; over-exposed photos (about 90 blobs) still take 20 to 40 s and fail, so callers should not shoot above the exposure where the marks wash out.

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
- **Debug output**: when fluxghost runs with debug-image writing enabled (`WRITE_DEBUG_IMG` in `fluxghost/debug.py`), the solve-pnp and check-pnp steps dump annotated PNGs (`solve-pnp-input.png`, `solve-pnp-matched.png`, `solve-pnp-corner.png`, `check_pnp.png`). `solve-pnp-matched.png` is the raw match labelled `<index>:<per-point score>` (anchor in magenta), written before points scoring < 0.1 are replaced by anchor + reference offset; `solve-pnp-corner.png` adds the returned points in cyan.
- **Frontend quirks** (`camera-calibration.ts`): the client keeps a single module-level socket (`cameraCalibrationApi`), still sends the deprecated `calibrate_fisheye` for fisheye lenses, and sends `dh` with `toFixed(2)`/`toFixed(3)` while the server re-rounds to 2 decimals.
