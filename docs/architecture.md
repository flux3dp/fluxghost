# FLUXGhost Architecture

FLUXGhost is the local websocket backend that sits between the Beam Studio frontend (TypeScript/Electron/web) and FLUX laser machines. It wraps the `fluxclient` machine-control library in a websocket API so the frontend never talks to hardware directly.

```
┌────────────────────────────────────────────────────────────┐
│  Beam Studio (Electron / web)                              │
│  packages/core/src/web/helpers/websocket.ts  (WS wrapper)  │
│  packages/core/src/web/helpers/api/*         (per-endpoint)│
└──────────────┬─────────────────────────────────────────────┘
               │  ws://127.0.0.1:<port>/ws/<endpoint>
┌──────────────▼─────────────────────────────────────────────┐
│  FLUXGhost  (this repo, Python 3.8)                        │
│  ghost.py → HttpServer (select loop)                       │
│    /ws/*  → http_websocket_route.py → websocket/* handlers │
│    api/*  → endpoint logic (mixins over WebSocketBase)     │
└──────┬───────────────┬───────────────┬─────────────────────┘
       │               │               │
  fluxclient       fluxsvg + beamify   OpenCV / PIL / SciPy
  (discovery,      (SVG parse &        (camera calibration,
  robot, camera,   rasterize for       image tracing,
  FCode toolpath)  toolpath)           contours)
       │
   FLUX machines  (LAN: UDP discovery + SSL/TCP; USB; UART)
```

## Process & Server Model

- **Entry point**: [ghost.py](../ghost.py). Parses CLI flags, sets up logging ([fluxghost/launcher.py](../fluxghost/launcher.py)), fetches SSL certs ([fluxghost/cert/fetch_certs.py](../fluxghost/cert/fetch_certs.py)), then runs `HttpServer.serve_forever()`.
- **Event loop**: single-threaded `select()` loop in [fluxghost/http_server_base.py](../fluxghost/http_server_base.py) multiplexing the HTTP socket, the optional HTTPS socket (port 8443, only if `fluxghost/cert/fullchain.pem` + `privkey.pem` exist), and device-discovery UDP sockets. Individual websocket connections are handled per-request; long-running work inside handlers uses threads where needed (e.g. toolpath computation).
- **Ports**:
  - Default `127.0.0.1:8000`; `--ip`/`--port` override.
  - `--port 0` auto-assigns; the chosen port is written to a `FluxStudioPort` file in the OS config dir and printed to stdout as `{"type": "ready", "port": <n>}` — **this stdout line is the contract with Beam Studio's `backend-manager.ts`**.
- **Lifecycle**: `--trace-pid <pid>` starts a watchdog thread that kills fluxghost when the parent (Electron) process exits.
- **Origin policy**: only localhost websocket origins are accepted unless `--allow-foreign` is passed (used for the Docker/server deployment).
- **HTTP proxy**: non-websocket requests under `/api/*` are proxied to the host in the `PROXY_API_HOST` env var ([fluxghost/http_handler.py](../fluxghost/http_handler.py)); static assets are served from `fluxghost/assets/`.

## Request Routing & Handler Layering

[fluxghost/http_websocket_route.py](../fluxghost/http_websocket_route.py) holds an ordered regex table. A `/ws/<path>` upgrade request is matched top-down and the handler class is imported lazily.

Handlers are layered in two halves:

1. **`fluxghost/websocket/*`** — transport. Each file subclasses `WebSocketBase` ([websocket/base.py](../fluxghost/websocket/base.py)), which owns the socket, query-string parsing, a 600 s idle timeout, and fatal-error handling. Frame encode/decode lives in [fluxghost/utils/websocket.py](../fluxghost/utils/websocket.py).
2. **`fluxghost/api/*`** — behavior. Each endpoint's logic is a *mixin factory* (`def xxx_api_mixin(cls): class XxxApi(cls): ...`) so the same logic can wrap different transports. [api/api_base.py](../fluxghost/api/api_base.py) provides the response helpers; [api/misc.py](../fluxghost/api/misc.py) provides `OnTextMessageMixin` (dispatch text commands via `self.cmd_mapping`) and `BinaryUploadHelper` (stateful chunked binary uploads).

## Endpoints

| Route (`/ws/` + …) | Handler (api/) | Purpose | Main Beam Studio client |
|---|---|---|---|
| `discover` | `discover.py` | Push LAN/USB device announcements; `poke <ip>`, `poketcp`, `testtcp` | `helpers/api/discover.ts` |
| `touch` | `touch.py` | Device trust/auth handshake (RSA key exchange, password) | `helpers/api/touch.ts` |
| `device-manager/{uuid\|usb/N\|uart/dev}` | `device_manager.py` | Device settings: name, password, wifi/network config | none — legacy, no frontend consumer |
| `control/{uuid\|usb/N}` | `control.py` (largest, ~830 lines) | Machine control: file ls/upload/rm, `play start/pause/resume/abort`, laser power, fan, `deviceinfo`, firmware update (`update_fw`, `update_mbfw`, `update_hbfw`), raw-mode gcode | `helpers/api/control.ts` (~1950 lines) |
| `camera/{uuid\|usb/N}` | `camera.py` | Camera frame streaming (binary JPEG frames + JSON metadata) | `helpers/api/camera.ts` |
| `camera-calibration` | `camera_calibration.py` | Charuco/fisheye calibration, distortion solving ([utils/camera/](../fluxghost/utils/camera/)) | `helpers/api/camera-calibration.ts` |
| `camera-transform` | `camera_transform.py` | Apply calibration transforms to camera images | `helpers/api/camera-transform.ts` |
| `svgeditor-laser-parser` | `svgeditor_toolpath.py` | SVG → gcode/FCode. Commands: `svgeditor_upload`, `divide_svg(_by_layer)`, `go`, `g2f`, `set_params`, `interrupt` | `helpers/api/svg-laser-parser.ts` |
| `image-tracer` | `image_tracer.py` | Raster image vectorization | none — frontend uses `imagetracerjs` in a web worker instead |
| `opencv` | `opencv.py` | Generic OpenCV image ops (sharpen etc.) | `helpers/api/open-cv.ts` |
| `utils` | `utils.py` | Misc: `pdf2svg`, `rgb_to_cmyk`, contour matching | `helpers/api/utils-ws.ts` |
| `push-studio` | `push_studio.py` | Inbound push channel for the Adobe Illustrator/AI extension | `helpers/api/ai-extension.ts` |
| `inter-process` | `inter_process.py` | IPC between studio instances | (niche) |
| `usb/interfaces`, `usb-config` | `usb_interfaces.py`, `usb_config.py` | Enumerate/configure USB & UART links | none — legacy, no frontend consumer |
| `ver` | `ver.py` | Pushes `{fluxghost, fluxclient}` versions on connect, then closes | connectivity checks |

## Message Protocol

Text frames are JSON objects keyed by `status`; binary frames (Blobs) carry file chunks, camera frames, and generated FCode.

| `status` | Meaning |
|---|---|
| `connecting` / `connected` | Connection to the *machine* (not the ws) progressing / established |
| `ok` | Command succeeded (may carry extra fields) |
| `error` | Recoverable failure — `{"status": "error", "error": "SYMBOL", ...}` |
| `fatal` | Unrecoverable; server closes the websocket |
| `continue` | Server is ready to receive binary payload chunks |
| `binary` | Next frame(s) are binary — `{"status": "binary", "size": n, "mime": ...}` |
| `progress` / `computing` / `transfer` / `uploading` | Long-operation progress |
| `complete` | Operation finished (with result metadata) |
| `pong` | Keep-alive reply (frontend pings every 60 s) |

Binary upload flow: client sends a command with a size (e.g. `svgeditor_upload <name> <size> ...`) → server replies `continue` → client streams binary chunks → `BinaryUploadHelper` reassembles → server replies `ok`.

Authenticated endpoints (`control`, `camera`, `touch`) begin with the client sending its RSA public key (generated by Beam Studio, `rsaKey()`); fluxghost passes it to `fluxclient.encryptor.KeyObject` for the device handshake.

## Beam Studio Integration

**Desktop (Electron)** — `apps/app/src/node/backend-manager.ts`:
1. Spawns the PyInstaller-built `flux_api` binary with `--port 0 --trace-pid <electron pid>` (or `--port 8000 --ip 0.0.0.0 --allow-foreign --assets ...` in server mode).
2. Watches stdout for `{"type": "ready", "port": n}` and broadcasts `BackendEvents.BackendUp` over IPC.
3. The renderer stores the port as `window.FLUX.ghostPort`; `helpers/websocket.ts` builds `ws://127.0.0.1:${ghostPort}/ws/<endpoint>` from it.
4. Auto-restarts the backend 2.5 s after a crash.

**Web (PWA)** — the page is HTTPS so plain `ws://localhost` is blocked. Two workarounds in beam-studio:
- `helpers/InsecureWebsocket.ts`: tunnels through the FluxTunnel Chrome extension via DOM custom events.
- `helpers/sslIpHelper.ts`: races WSS on port 8443 via `*.sslip.flux3dp.com` certificates against plain WS, first to connect wins.

## Dependencies

- **fluxclient** (git submodule `./fluxclient` → flux3dp/fluxclient-dev, or a sibling checkout): discovery, device managers, robot/camera protocols, FCode toolpath writers. Imported throughout `api/`.
- **fluxsvg** (public, github.com/flux3dp/fluxsvg) + **beamify** (package lives in `beamify/python`; C++ canvas-like drawing core in `beamify/src`) — only needed by `svgeditor-laser-parser`. fluxsvg is a CairoSVG fork that renders SVG onto beamify's surface instead of cairo's; it still loads native `libcairo` at import time via `cairocffi`. The prebuilt cairo dylibs in `lib/mac` are **x86_64-only** — on Apple Silicon dev machines use Homebrew cairo with `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib`.
- **OpenCV / PIL / NumPy / SciPy**: calibration, image tracing, contour work.

## Deployment

| Target | How |
|---|---|
| Desktop (bundled with Beam Studio) | `pyinstaller ghost.spec` → `dist/ghost/flux_api`; `lib/mac|win/...` dylibs bundled for cairo |
| Docker / server | `docker compose build` from the **parent** dir with sibling checkouts of fluxclient-dev, fluxsvg, beamify; runs `uv sync` then `setup.py install` for each lib; exposes 8000 |
| CI | GitHub Actions via `action.yml` / `index.js` (Node wrapper that drives the Python build) |

## Known Constraints & Debt

- **Python 3.8 pin** (EOL Oct 2024) blocks dependency upgrades (numpy 1.24, scipy 1.10). fluxclient itself claims 3.8+; the pin holder is this repo.
- Test coverage is import-smoke only (`ghost.py --test`); the command protocol has no automated tests.
- `--slic3r`/`--cura`/`--cura2` flags and parts of `simulate/` are FLUX Delta (3D printer) era leftovers; current machines are laser-only.
- Protocol documentation historically lived on the GitHub wiki (linked from beam-studio source comments); this file is the in-repo replacement.
