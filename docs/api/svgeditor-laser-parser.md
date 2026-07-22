# SVG Editor Laser Parser

`ws://127.0.0.1:<port>/ws/svgeditor-laser-parser`

Converts Beam Studio's layered SVG scenes into machine toolpaths. It has two independent pipelines: a **divide** pipeline (`upload_plain_svg` + `divide_svg`/`divide_svg_by_layer`) that splits an imported plain SVG into strokes/bitmap/colors (or per-layer) parts for the editor, and a **task** pipeline (`svgeditor_upload` + `go`, or `g2f`) that turns the scene into gcode / FCode v1 / FCode v2 binaries. The heavy lifting is delegated to `fluxsvg` (divide) and `fluxclient` (`SvgeditorImage`, `SvgeditorFactory`, `svgeditor2taskcode`, `gcode2fcode`).

- **Handler**: `fluxghost/api/svgeditor_toolpath.py` (mixin `laser_svgeditor_api_mixin`), wrapper `fluxghost/websocket/toolpath.py` (`WebsocketLaserSvgeditor`), routed in `fluxghost/http_websocket_route.py:23`
- **Beam Studio client**: `packages/core/src/web/helpers/api/svg-laser-parser.ts`

## Connection

No URL parameters, localhost-only unless `--allow-foreign`. Commands are plain-text messages: the first word is the command, the rest are parameters (`fluxghost/api/misc.py:30-45`, split with `maxsplit=1`). An unknown command raises `ValueError`, which is answered with `{"status": "Error", "message": "BAD_PARAM_TYPE"}` (`fluxghost/api/misc.py:50-52`). Sending a text message while a binary upload is in progress is a protocol error and triggers `{"status": "fatal", "symbol": ["PROTOCOL_ERROR"], "error": "PROTOCOL_ERROR"}` (`fluxghost/api/misc.py:46-48`).

Every incoming message is handled on a **new thread** (`fluxghost/api/svgeditor_toolpath.py:602-604`), which is what allows `interrupt` to be processed while a long `go`/`g2f`/`svgeditor_upload` computation is running.

Per-connection state (`fluxghost/api/svgeditor_toolpath.py:32-39`): `pixel_per_mm` (default 10), `svg_image`, `loop_compensation` (default 0.0), `is_task_interrupted`, `curve_engraving_detail`, `fcode_metadata`, plus `plain_svg` (set by `upload_plain_svg`) and `factory_kwargs` (set by `svgeditor_upload`).

## Commands

### `upload_plain_svg <name> <file_length>`

Uploads a raw SVG for later division (`fluxghost/api/svgeditor_toolpath.py:239-254`). Beam Studio uses `name` values `plain-svg` (file import) and `text-svg` (text-to-path), see `svg-laser-parser.ts:806,867`.

```
→ upload_plain_svg plain-svg 5123
← {"status": "continue"}
→ <binary: 5123 bytes of SVG>
← {"status": "ok"}
```

The buffer is stored as `self.plain_svg`; nothing is parsed yet.

### `divide_svg [-s <scale>]`

Divides the previously uploaded `plain_svg` via `fluxsvg.divide(...)` with the current `loop_compensation` (`fluxghost/api/svgeditor_toolpath.py:69-97`). `-s <float>` sets `params['scale']`. Any `encoding="UTF-16"` / `encoding="utf-16"` declaration is rewritten to `utf-8` first (`fluxghost/api/svgeditor_toolpath.py:75-76`).

The reply is a fixed sequence of named parts, each announced by a JSON header and followed by one binary frame:

```
← {"name": "strokes", "length": 1234}
← <binary: 1234 bytes (SVG)>
← {"name": "bitmap", "length": 5678, "offset": [x, y]}   # or length 0 + empty binary when no bitmap
← <binary>
← {"name": "colors", "length": 910}
← <binary>
← {"status": "ok"}
```

`offset` is only present when a bitmap exists (`fluxghost/api/svgeditor_toolpath.py:86-88`). The frontend (`divideSVG` in `svg-laser-parser.ts:534-582`) collects binary frames per `name` until the accumulated Blob size equals `length`, and stores the bitmap offset as `bitmapOffset`.

### `divide_svg_by_layer [-s <scale>]`

Same upload/flags as `divide_svg`, but uses `fluxsvg.divide_by_layer(...)` and returns one named part per SVG layer (`fluxghost/api/svgeditor_toolpath.py:99-142`):

- If the result contains a `nolayer` part, it is sent first (`:111-113`).
- `bitmap` is then sent (with `offset`, or `length: 0` + empty binary when `None`) (`:114-121`).
- Then **every** key in the result except `bitmap_offset` is sent as `{"name": <key>, "length": N}` + binary — note this loop includes `bitmap` and `nolayer` again, so those two parts are transmitted twice (`:122-136`).
- Finally `{"status": "ok"}`.

### `svgeditor_upload <name> <file_length> <thumbnail_length> [flags]`

Uploads the Beam Studio scene (thumbnail + SVG concatenated in a single binary payload) and parses it into a `SvgeditorImage` (`fluxghost/api/svgeditor_toolpath.py:144-237`). Resets `curve_engraving_detail`, `is_task_interrupted`, `factory_kwargs` and `pixel_per_mm` (back to 10) on every call (`:146,188,193-194`).

Positional args: `name`, `file_length` (total binary payload bytes), `thumbnail_length` (bytes of the payload that belong to the thumbnail). Flags (`:196-225`):

| Flag | Effect |
|---|---|
| `-model <model>` | Hardware profile for the SVG parse (default `fbb1b`) |
| `-ldpi` / `-mdpi` / `-hdpi` / `-udpi` | `pixel_per_mm` = 5 / 10 / 20 / 40 (deprecated, kept for the web version) |
| `-dpmm <float>` | `pixel_per_mm = round(value)` (preferred) |
| `-workarea <json [w,h]>` | Overrides the hardware work area (mm) for both `SvgeditorImage` and the later `SvgeditorFactory` |

Unrecognized tokens are ignored, which is why Beam Studio can still prepend deprecated model flags such as `-beamo`, `-pro`, `-hexa`, `-<model>` (`svg-laser-parser.ts:942-952`).

Flow:

```
→ svgeditor_upload scene.svg 240000 3210 -model fbb2 -mdpi -dpmm 10
← {"status": "continue"}
→ <binary chunk 1> ... <binary chunk N>        # Beam Studio sends 128 KB chunks
← {"status": "computing", "message": "Analyzing SVG - 42.0%", "percentage": 0.42, "translation_key": "analyzing_svg"}
   ... (repeats)
← {"status": "ok"}
```

The first `thumbnail_length` bytes are kept as the task thumbnail; the rest is the SVG (`:157-159`). `SvgeditorImage(thumbnail, svg_data, pixel_per_mm, loop_compensation=..., hardware=..., workarea=...)` is built with the progress callback above and the interrupt check (`:160-167`). If interrupted, the handler returns without any reply (`:175-177`). Parse failure sends `{"status": "Error", "message": "<exception>\n<file>, line: <n>"}` (`:182-184`).

### `go [<names>...] [flags]`

Generates the toolpath from the last `svgeditor_upload` (`fluxghost/api/svgeditor_toolpath.py:344-591`). Only tokens starting with `-` are interpreted (`:367-369`); Beam Studio actually sends `go <upload-name> -f <flags>` and the `-f`/names tokens are simply ignored (`svg-laser-parser.ts:646`).

Flags (`:370-514`), with the `svgeditor2taskcode` kwarg they set:

| Flag | Value | Effect |
|---|---|---|
| `-model <model>` | name | `hardware_name` (default `fbb1b`); also selects FCode version via `FCODE_VERSION_MAP` |
| `-film` | — | FCode metadata `CONTAIN_PHONE_FILM=1` |
| `-spin <y>` | float | `spinning_axis_coord`; if `>= 0` also sets metadata `ROTARY=1` and marks the task rotary |
| `-rotary-y-ratio <r>` | float | `rotary_y_ratio` |
| `-rotary-z-motion <b>` | JSON bool | `rotary_z_motion` (default true downstream) |
| `-prespray <x,y,w,h>` | floats | `prespray` area (printer modules) |
| `-temp` | — | Don't stream the result; write it to `/var/gcode/userspace/temp.fc` instead |
| `-gc` | — | Output plain gcode (`GCodeMemoryWriter`) instead of FCode |
| `-af [z]` | optional float | `enable_autofocus`, optional `z_offset` |
| `-fg` / `-mfg` | — | `support_fast_gradient` / `mock_fast_gradient` |
| `-vsl <v>` | float | `vector_speed_limit` (mm/min) |
| `-csl <v>` | float | `curve_speed_limit` (curve/3D engraving) |
| `-diode <x,y>` | floats | `support_diode` + `diode_offset` |
| `-diode-owe` | — | `diode_one_way_engraving` |
| `-acc <a>` | float | padding acceleration `acc` (default 4000) |
| `-min-speed <v>` | float | `min_speed` (downstream default 3) |
| `-rev` | — | `is_reverse_engraving` |
| `-mask <t,r,b,l>` | floats | `clip` rectangle (borderless/open-bottom) |
| `-cbl` | — | `custom_backlash` |
| `-mep <n>` / `-mpp <n>` | int | `min_engraving_padding` / `min_printing_padding` |
| `-mpc` / `-owp` | — | `multipass_compensation` / `one_way_printing` |
| `-ptp <n>` / `-pbp <n>` | int | `printing_top_padding` / `printing_bot_padding` |
| `-psw <n>` / `-psh <n>` | int | `printing_slice_width` / `printing_slice_height` |
| `-nv <v>` / `-npw <v>` | float | `nozzle_voltage` / `nozzle_pulse_width` (4C printer) |
| `-mof <json>` | object | `module_offsets` per layer module |
| `-ts <n>` / `-pts <n>` / `-ats <n>` | int | `travel_speed` / `path_travel_speed` / `a_travel_speed` (defaults here: 7500 / 7500 / downstream) |
| `-no-pwm` | — | `no_pwm` |
| `-job-origin <x,y>` | floats | `job_origin`; also sets `START_WITH_HOME=0` in metadata |
| `-acc-override <json>` | object | `acc_override` (per fill/path axis accelerations) |
| `-segment <b>` | JSON bool | `segment` (bitmap block splitting, default true downstream) |
| `-engraving-erode <v>` | float | `engraving_erode` (auto-shrink) |
| `-machine-limit-position <json>` | object | `machine_limit_position` |
| `-skip-prespray` / `-prespray-times <n>` | — / int | `skip_prespray` / `prespray_times` |
| `-expected-module <n>` | int | `expected_module` (detected layer-module id) |
| `-watt <n>` | int | `watt` |
| `-s-curve` | — | `s_curve` acceleration planning |

Flow (`:519-591`):

```
← {"status": "computing", "message": "Initializing", "percentage": 0.03, "translation_key": "initializing"}
← {"status": "computing", "message": "Calculating task path 12.4%", "percentage": 0.124, "translation_key": "calculating_task_path"}
   ... (progress quantized to steps of 1/500)
← {"status": "computing", "message": "Finishing", "percentage": 1.0, "translation_key": "finishing"}
← {"status": "complete", "length": 812345, "time": 421.5, "traveled_dist": 15230.2, "metadata": {"TIME_COST": "...", ...}}
← <binary: 812345 bytes of FCode/gcode>
```

Internals: a `SvgeditorFactory(pixel_per_mm, loop_compensation=..., workarea=?, hardware_name=...)` wraps the stored `svg_image` (`:256-261,516`), `fcode_metadata` gains `CREATED_AT`, `AUTHOR`, `SOFTWARE`, `START_WITH_HOME`, `3D_CURVE_TASK` (`:522-530`), and `svgeditor2taskcode(writer, factory, ...)` streams into the selected writer (`:547-553`). The FCode "magic number" sub-version is 4 for rotary or non-home-start tasks, else 3, and forced to 1 for FCode v1 (`:535-545`).

- With `-gc`: same flow, but the binary is plain gcode and `time`/`traveled_dist` are 0 and `metadata` is `{}` (`:532-534,554-556`).
- With `-temp`: no binary is streamed; instead `{"status": "complete", "file": "/var/gcode/userspace/temp.fc"}` (`:583-585`).
- The frontend accumulates binary frames until the Blob size equals `length` (`svg-laser-parser.ts:665-682`).

### `g2f <file_length> <thumbnail_length>`

Converts uploaded gcode into FCode **v1** (`fluxghost/api/svgeditor_toolpath.py:263-342`). The binary payload is `<thumbnail><gcode>`, where the thumbnail is a base64 data-URI (`data:image/png;base64,...`) that gets decoded and re-encoded as PNG through PIL (`:272-284`).

```
→ g2f 80000 3210
← {"status": "continue"}
→ <binary: 80000 bytes>
← {"status": "ok"}
← {"status": "computing", "message": "Initializing", "percentage": 0.03, ...}
← {"status": "computing", "message": "Calculating task path12.4%", ...}
← {"status": "computing", "message": "Finishing", "percentage": 1.0, ...}
← {"status": "complete", "length": 44321, "time": 88.0, "traveled_dist": 1234.5}
← <binary: 44321 bytes of FCode v1>
```

Uses `FCodeV1MemoryWriter('LASER', ...)` and `gcode2fcode(...)` with `travel_speed=7500` (`:297-306`). Unlike `go`, the `complete` message has no `metadata` field.

### `set_params <key> <value>`

See [set_params keys](#set_params-keys). Note the handler **always** ends with `{"status": "ok"}` (`fluxghost/api/svgeditor_toolpath.py:67`) — even after it has sent an `error` for an unknown key or an invalid `curve_engraving` value, so clients see the error message first and then an `ok`.

### `interrupt`

Sets `is_task_interrupted = True` and replies `{"status": "ok"}` (`fluxghost/api/svgeditor_toolpath.py:593-595`). See [Errors & Interruption](#errors--interruption).

## set_params keys

Handled in `fluxghost/api/svgeditor_toolpath.py:51-67`. The value is everything after the key (single `split()`, so values must not contain spaces — Beam Studio JSON-encodes `curve_engraving` without whitespace).

| Key | Value | Effect |
|---|---|---|
| `loop_compensation` | float, clamped to `>= 0` | Kerf-style closed-path compensation; used by `divide_svg`, `divide_svg_by_layer`, `SvgeditorImage` and `SvgeditorFactory` |
| `curve_engraving` | JSON object (`bbox`, `points`, `gap`, `safe_height`, `acceleration`) | Stored as `curve_engraving_detail`; passed to `svgeditor2taskcode` as `curve_engraving` and flips FCode metadata `3D_CURVE_TASK` to `1`. Invalid JSON → `{"status": "error", "message": "Invalid curve_engraving value"}` |
| `shading`, `one_way`, `calibration` | any | Accepted and ignored (legacy) |
| anything else | — | `{"status": "error", "message": "Unknown parameter <key>"}` |

Beam Studio calls `set_params loop_compensation <n>` and `set_params curve_engraving <json>` right before `go` (`svg-laser-parser.ts:653-663`).

## Binary Flows

**Upload (client → server).** Commands that expect binary (`upload_plain_svg`, `svgeditor_upload`, `g2f`) install a `BinaryUploadHelper(length, callback, ...)` and answer `{"status": "continue"}`. Every subsequent binary websocket frame is appended (`fluxghost/api/misc.py:73-89`); frames may be arbitrarily chunked (Beam Studio uses 128 KB chunks for `svgeditor_upload`, one blob otherwise). When the byte count reaches exactly `length` the callback runs and normal text-command mode resumes. Overshooting the declared length raises `BAD_LENGTH ...`, delivered as a `fatal` (`fluxghost/api/misc.py:17-26`). Binary frames sent while no helper is installed produce `{"status": "fatal", ..., "error": "BAD_PROTOCOL"}`.

**Download (server → client).** `go` and `g2f` first send the `complete` JSON containing `length`, then the entire generated file in a single `send_binary` call (`fluxghost/api/svgeditor_toolpath.py:574-581,321-324`). (The websocket layer may fragment it; the frontend just concatenates Blobs until the size matches `length`.) `divide_svg`/`divide_svg_by_layer` use the same header-then-binary pattern per named part but with `name`/`length` headers instead of `status: complete`.

## Errors & Interruption

- Computation/parse failures reply `{"status": "Error", "message": "<exception>\n<file>, line: <line>"}` — note the **capital-E** `Error`, which is what the frontend switches on (`svg-laser-parser.ts:679,913`). The exception is then re-raised into the handler thread (logged, connection stays open).
- `set_params` uses lowercase `{"status": "error", "message": ...}` for its two validation errors (`fluxghost/api/svgeditor_toolpath.py:62,66`).
- Protocol violations (`BAD_PROTOCOL`, `PROTOCOL_ERROR`, `BAD_LENGTH...`) arrive as `{"status": "fatal", "symbol": [...], "error": ...}` via `send_fatal` (`fluxghost/api/api_base.py:64-71`).
- **Interruption**: `interrupt` sets `is_task_interrupted`; because message handling is threaded it takes effect mid-computation. `check_interrupted()` (`fluxghost/api/svgeditor_toolpath.py:597-600`) returns true when the flag is set **or** the connection is no longer running, and is polled by `SvgeditorImage`, `svgeditor2taskcode` and `gcode2fcode`. An interrupted `svgeditor_upload`/`go`/`g2f` simply stops sending — no `ok`/`complete` follows (`:175-177,310-312,566-568`). `svgeditor_upload` and `go` clear the flag when they start (`:188,354`). Beam Studio discards the socket after interrupting (`interruptCalculation` → `resetWebsocket`, `svg-laser-parser.ts:685-698`).

## Example Session

Divide pipeline (importing a plain SVG into the editor):

```
→ upload_plain_svg plain-svg 5123
← {"status": "continue"}
→ <binary: 5123 bytes>
← {"status": "ok"}
→ divide_svg -s 3.52
← {"name": "strokes", "length": 2048}
← <binary 2048 bytes>
← {"name": "bitmap", "length": 0}
← <binary 0 bytes>
← {"name": "colors", "length": 1536}
← <binary 1536 bytes>
← {"status": "ok"}
```

Task pipeline (exporting the scene to FCode):

```
→ set_params loop_compensation 0
← {"status": "ok"}
→ svgeditor_upload scene.svg 240000 3210 -workarea [600.0,375.0] -fbb2 -model fbb2 -mdpi -dpmm 10
← {"status": "continue"}
→ <binary 128K chunk> × N
← {"status": "computing", "message": "Analyzing SVG - 50.0%", "percentage": 0.5, "translation_key": "analyzing_svg"}
← {"status": "ok"}
→ go scene.svg -f -model fbb2 -acc 8000 -spin 1875 -rotary-y-ratio 0.5 -min-speed 3 -ts 4000
← {"status": "computing", "message": "Initializing", "percentage": 0.03, "translation_key": "initializing"}
← {"status": "computing", "message": "Calculating task path 50.0%", "percentage": 0.5, "translation_key": "calculating_task_path"}
← {"status": "computing", "message": "Finishing", "percentage": 1.0, "translation_key": "finishing"}
← {"status": "complete", "length": 812345, "time": 421.5, "traveled_dist": 15230.2, "metadata": {...}}
← <binary: 812345 bytes FCode v2>
```

## Notes

- **Hardware model**: both the parse (`svgeditor_upload -model`) and the toolpath (`go -model`) default to `fbb1b` (Beambox) (`fluxghost/api/svgeditor_toolpath.py:149,357`). The model chosen at `go` time picks the FCode version via `fluxclient.hw_profile.FCODE_VERSION_MAP`: `fbm1`/`fbb1b`/`fbb1p`/`fhexa1` (and legacy aliases `beamo`/`beambox`/`beambox-pro`/`hexa`) → v1; `ado1`/`fbb2`/`fbm2`/`fhx2rf`/`fuv1` → v2. Unknown models fall back to v1 (`:374`).
- **FCode v1 vs v2**: v1 uses `FCodeV1MemoryWriter('LASER', metadata, thumbnails)` with magic number forced to 1; v2 uses `FCodeV2MemoryWriter(metadata, thumbnails, magic_number)` where the magic number is 4 for rotary tasks or `-job-origin` tasks and 3 otherwise (`:535-545`). `g2f` is always FCode v1.
- **pixel_per_mm / dpmm**: the SVG scene is interpreted at `pixel_per_mm` px per mm (default 10 = 254 dpi). Beam Studio sends both a legacy dpi flag and the newer `-dpmm <value>`; `-dpmm` wins because it is parsed last-match in the same loop (`:196-217`).
- **Loop compensation** is connection state set by `set_params`, not a `go` flag; it must be set *before* `svgeditor_upload`/`divide_svg` since it is baked into the parsed image (`:148,78,258`).
- **Curve engraving**: `set_params curve_engraving <json>` must also happen before `go`; it is cleared by every new `svgeditor_upload` (`:146`). It sets metadata `3D_CURVE_TASK=1` and is combined with `-csl` (curve speed limit) by the frontend (`svg-laser-parser.ts:261-273`).
- **Thumbnails**: for `go`, the task thumbnail embedded in the FCode comes from the first `thumbnail_length` bytes of the `svgeditor_upload` payload, via `factory.generate_thumbnail()` (`:537`). For `g2f` the client-provided base64 PNG data-URI is used directly.
- The `divide_svg_by_layer` response duplicates the `bitmap` (and `nolayer`) parts — they are sent once explicitly and once again by the generic key loop (`:111-136`). The frontend tolerates this because it re-keys parts by `name`.
