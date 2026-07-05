# Control

`ws://127.0.0.1:8000/ws/control/<uuid>` (also `ws://127.0.0.1:8000/ws/control/usb/<usb_addr>`)

Machine-control endpoint — the largest in fluxghost. It opens a robot session to one device (over LAN or host-to-host USB) and exposes a text command protocol for file management, job (play) control, device configuration, firmware updates, maintenance sub-tasks, and a raw/grbl pass-through mode. One websocket controls one device; the connection stays open for the whole control session.

- **Handler**: `fluxghost/api/control.py` (mixin, on top of `fluxghost/api/control_base.py`), wrapper `fluxghost/websocket/control.py`
- **Beam Studio client**: `packages/core/src/web/helpers/api/control.ts` (`Control` class, ~1950 lines)

Route patterns (`fluxghost/http_websocket_route.py:16-17`):

- `control/(?P<uuid>[0-9a-fA-F]{32})` — device UUID discovered over LAN
- `control/usb/(?P<usb_addr>[0-9]{1,3})` — host-to-host USB address

## Connection & Authentication

The first text message from the client must be the client's RSA key (Beam Studio sends `rsaKey()` in `onOpen`, `control.ts:186-188`). Everything after that is treated as a command (`fluxghost/api/control_base.py:102-123`).

Flow (`control_base.py:53-100`):

```
→ <RSA key PEM>
← {"status": "connecting", "stage": "discover"}
← {"status": "connecting", "stage": "connecting"}
← {"status": "connected"}
```

1. The key is parsed with `KeyObject.load_keyobj` (`control_base.py:107`). A `ValueError` produces fatal `KEYOBJ_BAD_PARAMS`; any other parse error produces fatal `RSA_BAD_PARAMS`.
2. `try_connect()` sends the `discover` stage, then looks the target up:
   - **uuid**: the device must be in `server.discover_devices`, otherwise fatal `NOT_FOUND` (`control_base.py:78`). The server then sends the `connecting` stage and opens a robot connection with the client key. Socket errors become fatal `DISCONNECTED`; robot errors are re-raised with their symbol (a `REMOTE_IDENTIFY_ERROR` also evicts the device from the discover cache, `control_base.py:72-75`).
   - **usb_addr**: the USB protocol object must exist in `g.USBDEVS`, otherwise fatal `UNKNOWN_DEVICE`; a `FluxUSBError` while opening becomes fatal `PROTOCOL_ERROR` (`control_base.py:80-94`).
3. On success the server sends `{"status": "connected"}`, raises the select-loop poll time to 30 s, and installs the command mapping (`control.py:38-139`).

Device password auth / retry (`type: "kick"` etc.) is **not** handled here — the robot connection either succeeds with the RSA key or fails with the symbols above. The frontend applies a 30 s connection timeout that restarts on every `connecting` message (`control.ts:19, 166-172`).

**Old firmware**: if the remote version is `< 1.0b13` the only registered command is `update_fw` (`control.py:42-47`).

Idle websockets are closed after 600 s without any incoming frame (`fluxghost/websocket/base.py:13, 59-72`).

## Command Protocol

Commands are plain-text messages, tokenized with `shlex.split` and resolved against a nested `cmd_mapping` tree (`control.py:164-198`), so multi-word commands like `file ls /SD` walk `file` → `ls` and pass `/SD` as the argument. Quoting works shell-style. An unmatched command yields `{"status": "error", "error": ["L_UNKNOWN_COMMAND"]}` (`control.py:201-202`).

Responses use the `ApiBase` helpers (`fluxghost/api/api_base.py`):

| status | shape | meaning |
|---|---|---|
| `ok` | `{"status": "ok", ...extra}` | command completed (`api_base.py:30-35`) |
| `error` | `{"status": "error", "error": ["SYMBOL", ...]}` | recoverable failure (`api_base.py:58-62`) |
| `fatal` | `{"status": "fatal", "symbol": [...], "error": "SYMBOL", "info"?: ...}` | session dead; the socket is closed right after (`api_base.py:64-71`, `websocket/base.py:45-47`) |
| `pong` | `{"status": "pong"}` | reply to `ping` (`control.py:182-183`) |
| `continue` | `{"status": "continue"}` | server ready to receive binary data (`api_base.py:43-44`) |
| `uploading` | `{"status": "uploading", "sent": <bytes>}` | upload progress (`control_base.py:135-136, 142-148`) |
| `transfer` | `{"status": "transfer", "completed": n, "size": total}` | download progress (`control.py:330-334`) |
| `binary` | `{"status": "binary", "mimetype": ..., "size": ...}` | binary frame(s) follow (`control.py:324` etc.) |
| `connecting` / `connected` | see above | connection phase only |
| `raw` (task name) | `{"status": "raw", "text": "..."}` | device output piped in raw mode (`control.py:819-823`) |

**Response `cmd` echo (DirtyLayer)**: every `ok` response with kwargs carries a `cmd` field echoing the request, because the frontend matches responses to commands by string. `file ls ...` echoes `"cmd": "ls"`, `play select ...` → `"select"`, `file mkdir` → `"mkdir"`, `file rmdir` → `"rmdir"`, `file cpfile` → `"cpfile"`; every other command echoes the full command string (`control.py:766-798`). Additionally, `device_status.prog` is stripped from `play report` responses when `st_id == 64` (completed) (`control.py:794-796`).

## Command Reference

### General

| command | behavior | response |
|---|---|---|
| `ping` | liveness check, bypasses command dispatch (`control.py:182`) | `{"status": "pong"}` |
| `kick` | kicks the current session owner on the device (`control.py:243-245`) | `ok` |
| `deviceinfo` | device info dict from the robot (`control.py:559-560`) | `ok` + info fields |
| `deviceinfo_flux` | extended info (`control.py:562-563`) | `{"status": "ok", "data": {...}}` |
| `cloud_validate_code` | cloud validation code (`control.py:565-566`) — unused by frontend | `{"status": "ok", "code": ...}` |
| `wait_status <status> [timeout=6.0]` | polls `report_play` every 0.2 s until `st_id` matches; names `idle`/`running`/`paused`/`completed`/`aborted` map to 0/16/48/64/128, or pass a numeric id (`control.py:571-592`) — unused by frontend | `ok`, or `error TIMEOUT` |
| `jsonrpc_req <json>` | forwards a JSON-RPC request to the **current sub-task** (raises `OPERATION_ERROR` if none); response is filtered to printable chars and parsed (`control.py:725-730`) | `{"status": "ok", "data": {...}}` |

Frontend: `kick`/`killSelf`, `deviceDetailInfo` (`deviceinfo`), `deviceInfoFlux`, `getCartridgeChipData`/`cartridgeIOJsonRpcReq` (`jsonrpc_req`, `control.ts:957-980`).

### File (`file ...`)

| command | behavior | response |
|---|---|---|
| `file ls <path>` | lists a directory; empty path or `/` returns the roots (`control.py:247-264`) | `{"status": "ok", "cmd": "ls", "path": ..., "directories": [...], "files": [...]}` — roots are `["SD", "USB"]` |
| `file lsusb` | lists USB drives (`control.py:266-269`) | `{"status": "ok", "cmd": "lsusb", "usbs": [...]}` |
| `file mkdir <path>` | only under `/SD/`, else `error NOT_SUPPORT` (`control.py:295-301`) | `ok` + `path` |
| `file rmdir <path>` | only under `/SD/`, else `error NOT_SUPPORT` (`control.py:303-309`) | `ok` + `path` |
| `file rm <path>` / `file rmfile <path>` | deletes a file (`control.py:311-314`) | `ok` + `path` |
| `file cp <src> <dst>` / `file cpfile <src> <dst>` | copies a file (`control.py:344-348`) | `ok` + `source`, `target` |
| `file info <path>` / `file fileinfo <path>` | file metadata; if the file has an embedded preview a `binary` header + binary frame precede the `ok` (`control.py:278-288`) | `[binary?]` then `ok` + info fields |
| `file md5 <path>` | MD5 hash (`control.py:290-293`) — unused by frontend | `ok` + `file`, `md5` |
| `file upload <mimetype> <size> [path]` | upload (see [Binary Transfers](#binary-transfers)); default target `#` = play buffer (`control.py:350-361`) | `continue` → `uploading`… → `ok` |
| `file download <path>` | download (see below) (`control.py:316-325`) | `continue`(left/size)… → `binary` → binary frame |
| `file download2 <path>` | download with `transfer` progress and a final `ok` (`control.py:327-342`) — unused by frontend | `transfer`… → `binary` → binary frame → `ok` |

Deprecated single-word aliases still registered at top level: `ls`, `select`, `mkdir`, `rmdir`, `rmfile`, `cpfile`, `fileinfo`, `upload` (`control.py:50-65`). The frontend still uses top-level `upload <mimetype> <size> <path>/<name>` when uploading to a path (`control.ts:494-496`).

Frontend: `ls`, `lsusb`, `fileInfo`, `deleteFile`, `downloadFile`, `upload` (`control.ts:409-503, 713-735`).

### Play (`play ...`)

Job control. All setters simply call the robot and answer bare `ok` (`control.py:432-526`).

| command | behavior |
|---|---|
| `play select <path>` | select an uploaded/on-device file for playing (`control.py:271-276`), `ok` + `path` |
| `play start` / `play pause` / `play resume` / `play abort` / `play restart` / `play quit` | job lifecycle, bare `ok` |
| `play preview` | `preview_play` — unused by frontend |
| `play report` | `{"status": "ok", "device_status": {...}}`; `device_status.st_id` is the state id, `prog` removed when completed (`control.py:568-569, 794-796`) |
| `play info` | metadata of the current task; each embedded preview image is announced with `{"status": "binary", "length": n, "mime": ...}` + binary frame, then `ok` + metadata (`control.py:594-600`) |
| `play get_laser_power` / `play set_laser_power <v>` / `play set_laser_power_temp <v>` | laser power get/set (persistent / this-job-only), getters answer `ok` + `value` |
| `play get_laser_speed` / `play set_laser_speed <v>` / `play set_laser_speed_temp <v>` | speed override |
| `play get_fan` / `play set_fan <v>` / `play set_fan_temp <v>` | fan override |
| `play set_origin_x <v>` / `play set_origin_y <v>` | job origin |
| `play get_door_open` | `ok` + `value` |
| `play get <key>` | generic player getter, `ok` + `value` (`control.py:504-506`) — unused by frontend |
| `play toolhead operation` / `play toolhead standby` / `play toolhead heater <index> <temp>` | toolhead control during play (`control.py:508-518`) — unused by frontend |
| `play press_button` | simulates a device button press during play (`control.py:520-522`) — unused by frontend |

Frontend: `select`, `start`, `pause`, `resume`, `abort` (with retry loop that polls `play report` until `st_id` is 64/128 then sends `play quit`, `control.ts:505-587`), `quit`, `restart`, `report`, `getPreview` (`play info`), and all the laser/fan/origin getters and setters (`control.ts:898-930`).

### Config & Pipe

| command | behavior | response |
|---|---|---|
| `config get <key>` | read device config (`control.py:611-612`) | `ok` + `key`, `value` |
| `config set <key> <value...>` | write; value tokens re-joined with spaces (`control.py:602-604`) | `ok` + `key` |
| `config set_json <key> <value...>` | write, value shell-quoted via `pipes.quote` (`control.py:606-609`) — unused by frontend | `ok` + `key` |
| `config del <key>` | delete (`control.py:614-616`) | `ok` + `key` |
| `pipe get/set/del <key> [...]` | same shape against `robot.pipe` (`control.py:618-627`) — unused by frontend | `ok` + `key` |

Frontend: `getDeviceSetting` / `setDeviceSetting` / `deleteDeviceSetting` (`control.ts:932-936`).

### Firmware & calibration-data upload

All follow the upload flow in [Binary Transfers](#binary-transfers) using `simple_binary_receiver`; on success the server sends `ok` and then **closes the websocket** (`control.py:363-430`).

| command | behavior |
|---|---|
| `update_fw <mimetype> <size>` | machine firmware (`control.py:378-379`); frontend sends `update_fw binary/flux-firmware <size>` (`control.ts:1879-1885`) |
| `update_mbfw <mimetype> <size>` | mainboard firmware (`control.py:381-382`) |
| `update_hbfw <mimetype> <size>` | headboard/toolhead firmware (`control.py:384-385`) |
| `update_laser_records <mimetype> <size>` | laser usage records (`control.py:387-400`) — unused by frontend |
| `update_fisheye_params <mimetype> <size>` | fisheye camera calibration JSON (`control.py:402-415`); frontend `uploadFisheyeParams` |
| `update_fisheye_3d_rotation <mimetype> <size>` | fisheye 3D rotation JSON (`control.py:417-430`); frontend `updateFisheye3DRotation` |

The `mimetype` argument is accepted but ignored for the three firmware commands (`_` parameter). A `RobotError` during the device-side update is reported as `error <symbol>` instead of `ok`.

### Fetch (device → client downloads)

All use the same download flow: repeated `{"status": "transfer", "completed": n, "size": total}`, then `{"status": "binary", "mimetype": ..., "size": ...}`, one binary frame, and a final `ok` (`control.py:629-723`).

| command | content |
|---|---|
| `fetch_log <logname>` | device log file (`control.py:629-643`); frontend `downloadLog` |
| `fetch_laser_records` | laser records (`control.py:645-659`) — unused by frontend |
| `fetch_camera_calib_pictures <filename>` | calibration picture (`control.py:661-675`); frontend `fetchCameraCalibrateImage` |
| `fetch_fisheye_params` | fisheye calibration JSON (`control.py:677-691`); frontend `fetchFisheyeParams` |
| `fetch_fisheye_3d_rotation` | fisheye 3D rotation JSON (`control.py:693-707`); frontend `fetchFisheye3DRotation` |
| `fetch_auto_leveling_data <data_type>` | auto-leveling data; frontend passes `bottom_cover` / `hexa_platform` / `offset` (`control.py:709-723`, `control.ts:863-895`) |

### Tasks & raw mode (`task ...`)

`task <type>` switches the session into a sub-task; while a task is active, **normal command dispatch is bypassed** (`control.py:185-193`).

| command | behavior |
|---|---|
| `task raw` | opens the device's raw (grbl-style) socket and pipes it to the websocket (`control.py:548-552`) |
| `task auto_cover` / `task cartridge_io` / `task red_laser_measure` / `task z_speed_limit_test` | starts the named maintenance task on the robot (`control.py:535-546`); unknown types answer `error Unknown task: <type>` |
| `task quit` | quits the active task (`control.py:554-557`), `ok` + `task: ""` |

On success the server answers `{"status": "ok", "task": "<type>", "cmd": "task <type>"}`.

**While a sub-task (non-raw) is active** (`control.py:752-764`): every text message except `quit`/`task quit` and `jsonrpc_req ...` is sent verbatim to the device backend (`make_cmd`) and the raw device reply is returned as `{"status": "ok", "data": "<reply>", "cmd": ...}`. This is how the frontend implements `takeReferenceZ` (`take_reference_z(...)`), `measureZ` (`measure_z(...)`) for `red_laser_measure`, and `set_speed <v>` / `start` for `z_speed_limit_test` (`control.ts:999-1085`). `checkTaskAlive` sends a lone space and checks whether the reply data contains `KICKED` (`control.ts:988-997`).

**While raw mode is active** (`control.py:744-750, 803-826`): each text message is written to the raw socket with a trailing `\n`; the special message `raw home` is translated to `$H\n`. Device output is pushed asynchronously as `{"status": "raw", "text": "..."}` frames. `quit` or `task quit` leaves raw mode. If the raw socket died, the server answers `error TASK_SOCKET_CLOSED` and quits the task; if the pipe reads EOF it sends fatal `DISCONNECTED` (`control.py:819-826`).

Everything the frontend sends in raw mode (`$X`, `$H`, `$HCAM`, `$HZ`, G-code moves via `rawMove`, `B34`/`B35`-style vendor commands, line-check `N<n>...*<checksum>` framing, etc., `control.ts:1087-1853`) is device firmware protocol, not fluxghost commands — fluxghost only pipes bytes.

Frontend: `enterSubTask`/`endSubTask` (`task <mode>` / `task quit`), `enterRawMode` (`task raw`), `quitTask`.

## Binary Transfers

### Upload (client → device)

Used by `file upload`, deprecated `upload`, `update_*fw`, `update_laser_records`, `update_fisheye_params`, `update_fisheye_3d_rotation`.

```
→ file upload application/fcode 12345          (or: upload <mime> <size> <path>)
← {"status": "continue"}
→ <binary frame> ...                            (client chunks; Beam Studio uses 4096-byte chunks)
← {"status": "uploading", "sent": <bytes>}      (progress, throttled to 1% steps for file upload)
← {"status": "ok"}
```

Two implementations in `control_base.py`:

- `simple_binary_transfer` (`control_base.py:138-155`) streams chunks straight to the device and reports `uploading` at most once per percentage point.
- `simple_binary_receiver` (`control_base.py:157-174`) buffers the whole payload in memory first (used by firmware/calibration updates, which then report `uploading` per device-side callback); receiving more bytes than announced is fatal `NOT_MATCH`.

While a `binary_handler` is armed, incoming binary frames are fed to it; a binary frame with no armed handler is fatal `PROTOCOL_ERROR` (`control_base.py:125-133`). If no binary data arrives for 60 s the server sends fatal `TIMEOUT WAITING_BINARY` and closes (`websocket/base.py:59-61`).

### Download (device → client)

```
→ file download /SD/example.fc
← {"status": "continue", "left": 8192, "size": 12345}    (progress; `transfer` variant for fetch_*/download2)
← {"status": "binary", "mimetype": "application/fcode", "size": 12345}
← <one binary frame with the whole payload>
← {"status": "ok"}                                        (fetch_* and download2 only; plain `file download` ends at the binary frame)
```

`play info` uses a different header for its preview images: `{"status": "binary", "length": n, "mime": ...}` via `send_binary_begin` (`api_base.py:55-56`, `control.py:597-599`).

## Errors

- `error` responses carry `"error": ["SYMBOL", ...]` (always a list). Sources: `RobotError.error_symbol` (device-side errors, e.g. `NOT_SUPPORT`, `OPERATION_ERROR`), `RuntimeError` args, or fluxghost-local symbols `L_UNKNOWN_COMMAND` and `TIMEOUT` (from `wait_status`) (`control.py:200-217`).
- `fatal` responses end the session — the socket is closed immediately after (`websocket/base.py:45-47`). Sources (`control.py:208-241`, `control_base.py:105-133`):
  - `RobotSessionError` / `FluxUSBError` symbols (e.g. being kicked by another client),
  - `TIMEOUT` when a robot socket operation timed out,
  - `DISCONNECTED` on broken pipe,
  - connection phase: `KEYOBJ_BAD_PARAMS`, `RSA_BAD_PARAMS`, `NOT_FOUND`, `UNKNOWN_DEVICE`, `PROTOCOL_ERROR`, `DISCONNECTED`,
  - binary phase: `PROTOCOL_ERROR` (unexpected binary), `NOT_MATCH` (length overrun), `TIMEOUT WAITING_BINARY`.
- Unexpected exceptions answer `error L_UNKNOWN_ERROR` with a `traceback` array (`api_base.py:73-82`, `control.py:230, 239-241`).
- Idle timeout: no frames from the client for 600 s closes the websocket (`websocket/base.py:63-72`).

## Example Session

```
# connect to ws://127.0.0.1:8000/ws/control/0123456789abcdef0123456789abcdef
→ -----BEGIN RSA PRIVATE KEY----- ... (client key)
← {"status": "connecting", "stage": "discover"}
← {"status": "connecting", "stage": "connecting"}
← {"status": "connected"}

→ deviceinfo
← {"status": "ok", "version": "...", "model": "...", ..., "cmd": "deviceinfo"}

→ file upload application/fcode 30720
← {"status": "continue"}
→ <binary chunk> × 8
← {"status": "uploading", "sent": 12288}
← {"status": "ok", "cmd": "file upload application/fcode 30720"}

→ play start
← {"status": "ok", "cmd": "play start"}

→ play report
← {"status": "ok", "device_status": {"st_id": 16, "prog": 0.42, ...}, "cmd": "play report"}
```

## Notes

- The `cmd` echo and the `prog` stripping live in a subclass literally named `DirtyLayer` (`control.py:766-798`) — they exist because the frontend correlates responses with requests by string matching. Removing or renaming any command is a cross-repo breaking change.
- `shlex.split` means arguments with spaces must be quoted; `list_file`/`select_file`/`fileinfo` additionally re-join extra positional args with spaces to tolerate unquoted filenames (`control.py:247-249, 271-273, 278-280`).
- The frontend serializes commands through a task queue (max 30 pending) and one in-flight command at a time (`control.ts:95-132`), because the backend has no request ids — responses are matched purely by order.
- Backend commands never called by the current Beam Studio frontend: `file md5`, `file download2`, `play preview`, `play get`, `play toolhead *`, `play press_button`, `wait_status`, `cloud_validate_code`, `update_laser_records`, `fetch_laser_records`, `config set_json`, and the whole `pipe` group.
- `mkdir`/`rmdir` are restricted to `/SD/`; other locations answer `error NOT_SUPPORT` (`control.py:295-309`).
