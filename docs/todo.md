# TODO / Findings

Issues found while reviewing, building, and testing the stack (2026-07-05). Ordered roughly by impact.

## Build & Platform

- [ ] **`lib/mac` cairo dylibs are x86_64-only.** `libcairo.2.dylib` and friends fail to `dlopen` on Apple Silicon (`incompatible architecture (have 'x86_64', need 'arm64')`), so a native arm64 PyInstaller build would ship a broken `svgeditor-laser-parser`. Rebuild them as universal (or arm64) binaries. Dev workaround documented in CLAUDE.md: `brew install cairo` + `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib`.
- [ ] **Python 3.8 pin** (`requires-python = ">=3.8,<3.9"`) — EOL since Oct 2024; blocks numpy/scipy upgrades (stuck at numpy 1.24 / scipy 1.10). fluxghost is the pin holder; fluxclient builds fine on newer Pythons. Plan a 3.11+ migration.
- [ ] **fluxclient has intentionally ancient pins** — `pyasn1==0.1.9`, `pyusb==1.0.2` — tied to device auth/USB protocol code. Verify against real hardware and either bump or document why they must stay.

## Dead / Misleading Code

- [ ] **`--simulate` / `-s` flag is dead.** `ghost.py` parses `options.simulate` but nothing reads it. The simulated device (uuid `000…0`) actually registers under `--debug` / `-d` (`fluxghost/http_server_base.py:96-100`). Either wire `-s` to register `SimulateDevice` (and keep `-d` for log level only), or remove the flag.
- [ ] **Delta-era (3D printer) fossils**: `--slic3r`/`--cura`/`--cura2` flags + `GHOST_SLIC3R`/`GHOST_CURA*` env vars in `ghost.py`; the simulated filesystem serves `.fc` 3D-print models (`tower_of_pi.fc`, `Curiosity/…`); Bootstrap-era static assets in `fluxghost/assets/`; scanner/printer paths in fluxclient (`toolpath/printer/`, parts of `commands/`). Prune or clearly mark legacy.
- [ ] **Dead `_run_auth` in `fluxghost/api/touch.py`** — unused function kept alongside the live auth flow.
- [ ] **Wrapper docstrings show wrong routes** — `websocket/push_studio.py` and `websocket/inter_process.py` docstrings say `/ws/push_studio` / `/ws/inter_process`, but the real routes are hyphenated (`push-studio`, `inter-process`, see `http_websocket_route.py:27-28`).
- [ ] **`CameraWrapper` TODO** (`fluxghost/api/camera.py`): reaches into `camera.sock.fileno()`; `SimulateCamera` fakes a `.sock` property just to satisfy it. Change to `camera.fileno()`.

## Unused / Legacy Endpoints (candidates for removal)

Grep of beam-studio `packages/core/src/web` found **no frontend consumer** for these routes:

- [ ] `device-manager/*` (uuid / usb / uart variants) — machine settings sessions; superseded by newer flows
- [ ] `usb-config` — UART setup endpoint; its `SIMULATE` port path is also broken (missing `version`/`nickname`/`uuid` attrs)
- [ ] `usb/interfaces` — h2h USB enumeration (gates the `/usb/<addr>` variants of control/camera, so check before removing)
- [ ] `image-tracer` — frontend traces with `imagetracerjs` in a web worker instead
- [ ] `inter-process` — inbound relay for the Adobe Illustrator plugin (external caller, not beam-studio; keep but document)
- [ ] Deprecated top-level control commands (`ls`, `select`, `mkdir`, `rmdir`, `rmfile`, `cpfile`, `fileinfo`, `upload`) — replaced by the `file`/`play` trees, marked `# deprecated` in `control.py`

Decide: delete, or keep and mark as external-plugin/legacy API. If any are kept for third-party integrations, say so in docs/api/.

## Protocol Quirks (documented in docs/api/, fix when convenient)

- [ ] **Route regexes are prefix-matched, unanchored at the end** (`http_websocket_route.py` uses `re.match`) — e.g. `/ws/verbose` would match the `ver` route. Harmless today, but anchor with `$` to be safe.
- [ ] **`inter-process` crashes if no push-studio handler is registered** — relaying to `server.push_studio_ws` raises an unhandled `AttributeError` when Beam Studio hasn't called `set_handler` yet (`fluxghost/api/inter_process.py:26`). Guard and return an error payload instead.
- [ ] **`discover` replies plain-text `BAD_PARAMS`** (not JSON) for malformed poke commands — inconsistent with the JSON `status` protocol.
- [ ] **`touch` closes the socket silently on malformed JSON** — no error reply, the frontend just sees a close.
- [ ] **`svgeditor-laser-parser` inconsistent error casing** — `divide_svg` failures reply `{"status": "Error"}` (capital E) while the rest of the protocol uses lowercase `error`; and `set_params` replies `ok` even when the value failed to parse (`fluxghost/api/svgeditor_toolpath.py:51-67`).
- [ ] **`divide_svg_by_layer` transmits the `bitmap`/`nolayer` parts twice** — duplicated send block in `fluxghost/api/svgeditor_toolpath.py`; wasted bandwidth on every layered divide.
- [ ] **`utils` endpoint: `select_font` is missing a return/response path** in one branch (`fluxghost/api/utils.py`), and beam-studio's `utils-ws.ts` has an orphaned `upload` method calling a backend command that doesn't exist.
- [ ] **`opencv` endpoint caches uploaded images per connection but never evicts them** — the history deque bounds names, not the `imgs` dict; a long-lived connection uploading many images grows memory unbounded (`fluxghost/api/opencv.py`).
- [ ] **`camera-transform` has unreachable commands** — `set_fisheye_height`, `set_crop_param`, and `set_3d_rotation` are defined but not wired into the dispatch, so clients cannot call them; height is effectively fixed at 0. Note this interacts with the recent "Add set_fisheye_height in set_fisheye_matrix" work (`fluxghost/api/camera_transform.py`).
- [ ] **`camera-calibration` `cmd_solve_pnp_calculate` is missing a `return`** in one branch, falling through after replying (`fluxghost/api/camera_calibration.py`).
- [ ] **`camera-transform` can pass a PIL object to `send_binary`** when no transform params are set, instead of encoded bytes (`fluxghost/api/camera_transform.py`).
- [ ] **Websocket `_send` is not thread-safe** — `fluxghost/utils/websocket.py:_send` writes the frame header and payload as separate unlocked `send()` calls while message handling can be threaded, so concurrent sends interleave and corrupt framing. Reproduced during `svgeditor-laser-parser` `go` + `interrupt`: the interrupt ack and progress frames can desync the stream. Beam Studio survives only because it discards the socket right after interrupting. Add a per-connection send lock. (Pinned by `tests/usage/test_toolpath.py` P10, which byte-scans instead of frame-parsing.)
- [ ] **`SimulateDevice` is missing `simulate_start_player`** — `SimulateRobot.start_play` calls it but `SimulatePlayerMixIn` (`fluxghost/simulate/device.py`) never defines it, so `play select` + `play start` against the simulator answers `error L_UNKNOWN_ERROR` instead of `ok`. Add the method so the play flow is testable without hardware. (Pinned by `tests/usage/test_control.py` C8.)
- [ ] **Keep-alive `ping` is unhandled on `OnTextMessageMixin` endpoints** — Beam Studio's websocket wrapper sends `ping` after 60 s idle on *every* socket, but toolpath/utils/opencv/image-tracer have no `ping` in `cmd_mapping`, so the reply is `{"status": "Error", "message": "BAD_PARAM_TYPE"}` (`fluxghost/api/misc.py:44-52`) — and capital-E `Error` bypasses the frontend's lowercase-`error` switch case (`websocket.ts:179`), landing in whatever stale onMessage handler is registered. Add a shared `ping`→`pong` in the mixin.
- [ ] **`push_studio_ws` handler slot is never cleared on disconnect** (`fluxghost/http_server_base.py`) — after a Beam Studio tab closes, the slot still points at the dead socket until another tab re-registers; combined with the `inter-process` AttributeError above, a publisher then gets a raw TCP EOF with no error frame. Clear the slot on socket close and guard the relay.

## Testing

- [x] ~~No protocol-level tests~~ → **`tools/ws_smoke.py` added 2026-07-05**: spawns the server with `-d`, runs 8 protocol checks (ver, discover, touch, control ×3, camera, toolpath divide_svg) with a stdlib-only websocket client; `ALL PASS` verified. Remaining follow-ups:
  - [ ] Port it into `tests/` as pytest cases and run in CI (needs no hardware; toolpath check needs fluxsvg/beamify installed in the CI image — the Docker build already has them).
  - [ ] Extend coverage to camera-calibration, utils, and opencv endpoints (the `WS` helper class in `tools/ws_smoke.py` is reusable).
- **fluxclient-dev test audit (2026-07-05)** — the legacy suite is plain `unittest` (pytest is not installed anywhere), has **no CI step** (`build_package.yml` never runs tests, unlike fluxghost's workflows which do run `ghost.py --test`), and requires `python setup.py build_ext --inplace` first (running from the repo root shadows the installed package, so the compiled `_toolpath` extension is missing otherwise). Status per module — 23 collected, 14 pass:
  - [ ] `tests/toolpath/test_gcode_tools.py` — best of the lot: all 3 GCodeParser tests pass; 11/17 GCodeWriter tests pass, the 6 failures are **Delta-era expectation drift, not bugs** (writer now emits grbl `$H` for home instead of `G28`, `G1S`/`G1V` laser power instead of `X2O<n>` toolhead PWM, `M25 ` with trailing space). Update the expected strings and this becomes a healthy native-extension regression suite. Note `assertDictContainsSubset` is removed in Python 3.12 — fine on 3.8, fix when unpinning.
  - [ ] `tests/cli/test_fcode_cli.py` — runs; its single g2f→f2g roundtrip test fails on the same `G28`→`$H` drift. Easy fix.
  - [ ] `tests/upnp/test_discover.py` — dead import (`fluxclient.upnp.UpnpDiscover`; the package was renamed). `DeviceDiscover.source_filter` still exists (`fluxclient/device/discover.py:247`), so this is a rename-and-move fix.
  - [ ] `tests/cli/test_device_related_cli.py` — mostly dead: imports removed modules (`fluxclient.commands.scan`, `fluxclient.commands.upnp`) and `tests/real_device.py` (which also imports `fluxclient.upnp`). The discover-timeout test and the hardware-gated camera/robot tests are worth porting to `fluxclient.device`/`flux_manager`; the scanner tests should be deleted.
  - [ ] `tests/sdk/test_sdk.py` — empty stub (`test_dot: pass`), not even collected (missing `__init__.py` in `sdk/`). Delete.
  - [ ] Root `conftest.py` configures logging/tempdir but is pytest-only; under `unittest` it never loads, so the `conftest.ini` real-device config flows only through `tests/real_device.py`. Decide on one runner (pytest, given `conftest.ini.example` implies it) and add a CI step.

## Documentation

- [x] ~~Both READMEs are Delta-era~~ → **rewritten 2026-07-05**: current laser-era quick start + doc links up top, Delta-era content preserved under "Legacy Notes" sections in both repos.
- [ ] **GitHub wiki links in beam-studio source** (`discover.ts`, `camera.ts`, `svg-laser-parser.ts` reference `github.com/flux3dp/fluxghost/wiki/...`) — update to point at the in-repo `docs/api/*.md` once merged.
