# Usage-Based Test Plan (tests/usage/)

Protocol tests derived from how Beam Studio actually drives fluxghost — each case maps to a real frontend call site in `beam-studio/packages/core/src/web/helpers/api/*`. Independent from the quick smoke suite (`tools/ws_smoke.py`); this is the regression suite, that is the pre-flight check.

Run:

```sh
uv run python -m unittest discover -s tests/usage -t . -v
```

Each module spawns its own server (`ghost.py -d --port 0`) via `tests/usage/_harness.py`, so modules are independent and parallel-safe. No hardware needed. Tests that pin a known quirk say so — if you fix the quirk, update the test and check it off in [todo.md](todo.md).

**Status: fully implemented, 39 tests, all passing (verified 2026-07-05, 17.6 s wall clock).** Deviations from the original plan discovered during implementation:

- **C8** pins an `error L_UNKNOWN_ERROR` instead of `ok` — the simulator is missing `simulate_start_player` (see todo.md). Flip the assertion when that's fixed.
- **P10** verifies interrupt via raw byte-scanning because concurrent server sends corrupt websocket framing (thread-unsafe `_send`, see todo.md). Re-frame it once a send lock exists.
- **X3**'s no-handler behavior is a raw TCP EOF (no error frame, no close frame), and it must run before any `set_handler` test because the handler slot is never cleared (see todo.md).
- **U2/U3** landed on `split_color` (full-color layer splitting) and `get_convex_hull` (framing feature); `pdf2svg` was skipped as it needs an external binary.
- The M2/M3 camera assertions use PNG magic — the simulator pushes `flux-icon.png`, while real hardware streams JPEG.

**Known coverage gaps (reviewed 2026-07-05):**

- **`camera-calibration` and `camera-transform` have no tests** — the largest gap. Both are heavily used by Beam Studio's calibration wizards and are pure computation (no hardware needed); tests require synthetic chessboard/charuco fixture images (generable with OpenCV) and fisheye parameter fixtures. Highest-value next addition.
- **Control `file upload`/`download`, `config set/get`, and `fetch_*` families are untested** — blocked on `SimulateRobot` missing the corresponding methods (`upload_stream`, config ops), the same class of gap as `simulate_start_player` (see todo.md). Extend the simulator first.
- **Keep-alive `ping` is only tested on `control`** — on OnTextMessageMixin endpoints it currently yields `Error BAD_PARAM_TYPE` (see todo.md); add a cross-endpoint ping test once fixed.
- **`utils` `pdf2svg` untested** (needs the external `pdf2svg` binary); `upload_to`/`check_exist`/`select_font` untested (trivial file ops; `select_font` has a known missing-return bug).
- **M3 camera cadence** has a 0.5 s lower bound that could flake if trigger-pipe bytes queue during a slow handshake — loosen to 0.4 s if it ever fires in CI.

| # | Case | Frontend source | Module |
|---|---|---|---|
| L1 | `--port 0` prints `{"type":"ready","port":N}` on stdout | `backend-manager.ts` | test_lifecycle_discover_touch |
| L2 | `/ws/ver` pushes `{fluxghost, fluxclient}` then closes | manual/ops | test_lifecycle_discover_touch |
| D1 | discover announcement carries all fields the frontend reads | `discover.ts` | test_lifecycle_discover_touch |
| D2 | `poke 127.0.0.1` is accepted | `discover.ts` | test_lifecycle_discover_touch |
| D3 | malformed poke → current `BAD_PARAMS` reply (quirk pinned) | — | test_lifecycle_discover_touch |
| T1 | touch simulate auth: `serial/name/has_response/reachable/auth` | `touch.ts` | test_lifecycle_discover_touch |
| T2 | touch malformed JSON → silent close (quirk pinned) | — | test_lifecycle_discover_touch |
| C1 | control handshake stages discover→connecting→connected | `control.ts` | test_control |
| C2 | garbage RSA key → fatal | `control.ts` | test_control |
| C3 | unknown uuid → fatal `NOT_FOUND` | `control.ts` | test_control |
| C4 | `ping` → `{"status":"pong"}` | `control.ts` keep-alive | test_control |
| C5 | `file ls SD` → `cmd:"ls"` echo + directories/files + ok | `control.ts` | test_control |
| C6 | `file ls <bogus>` → error symbol | `control.ts` | test_control |
| C7 | `play report` → `device_status.st_label == IDLE` | `control.ts` | test_control |
| C8 | `play select` + `play start` → ok | `control.ts` | test_control |
| C9 | unknown command → `L_UNKNOWN_COMMAND` | — | test_control |
| C10 | `kick` → ok | `control.ts` | test_control |
| M1 | camera handshake → connected | `camera.ts` | test_camera |
| M2 | ≥2 auto-pushed PNG frames | `camera.ts` | test_camera |
| M3 | sustained frame cadence (~4 fps, loose bound) | `camera.ts` | test_camera |
| P1 | `upload_plain_svg` single-frame → ok | `svg-laser-parser.ts` | test_toolpath |
| P2 | upload chunked at 128 KB (frontend chunk size) → ok | `svg-laser-parser.ts` | test_toolpath |
| P3 | `divide_svg` → strokes/bitmap/colors + ok | `svg-laser-parser.ts` | test_toolpath |
| P4 | `divide_svg -s <scale>` | `svg-laser-parser.ts` | test_toolpath |
| P5 | `divide_svg_by_layer` (duplicate-send quirk pinned) | `svg-laser-parser.ts` | test_toolpath |
| P6 | `set_params loop_compensation` → ok | `svg-laser-parser.ts` | test_toolpath |
| P7 | `svgeditor_upload` with layered Beam Studio SVG → ok | `svg-laser-parser.ts` | test_toolpath |
| P8 | `go` → progress → binary FCode (`FCx` magic) | `svg-laser-parser.ts` | test_toolpath |
| P9 | `g2f` → gcode-to-fcode output | `svg-laser-parser.ts` | test_toolpath |
| P10 | `interrupt` during task (best effort) | `svg-laser-parser.ts` | test_toolpath |
| U1 | `rgb_to_cmyk` | `utils-ws.ts` | test_image_utils |
| U2 | second real utils command (per docs/api/utils.md) | `utils-ws.ts` | test_image_utils |
| U3 | third real utils command | `utils-ws.ts` | test_image_utils |
| O1 | opencv `upload` + `sharpen` → binary result | `open-cv.ts` | test_image_utils |
| X1 | `push-studio` `set_handler` → ok | `ai-extension.ts` | test_push_channel |
| X2 | `inter-process` `adobe_illustrator` relays to push-studio ws | AI plugin | test_push_channel |
| X3 | relay without registered handler (current behavior pinned) | — | test_push_channel |

Notes:
- The toolpath module requires fluxsvg/beamify installed and native cairo reachable via `DYLD_FALLBACK_LIBRARY_PATH` (`/opt/homebrew/lib` on Apple Silicon, `/usr/local/lib` on Intel); the harness sets the arch-appropriate path automatically and the module must skip cleanly when the route is unavailable.
- "Quirk pinned" tests assert today's behavior on purpose so a fix shows up as a deliberate test change, not silent drift.
