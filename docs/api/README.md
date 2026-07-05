# FLUXGhost Websocket API Reference

One document per websocket endpoint. All endpoints live under `ws://127.0.0.1:<port>/ws/<route>`; routing is defined in [`fluxghost/http_websocket_route.py`](../../fluxghost/http_websocket_route.py). For the overall picture (server model, message protocol, Beam Studio integration) see [../architecture.md](../architecture.md); for known issues see [../todo.md](../todo.md).

## Endpoints

| Doc | Route | Purpose | Beam Studio consumer |
|---|---|---|---|
| [discover.md](discover.md) | `/ws/discover` | Server-push device announcements (LAN/USB) | `helpers/api/discover.ts` |
| [touch.md](touch.md) | `/ws/touch` | Device trust/auth handshake (RSA key + password) | `helpers/api/touch.ts` |
| [control.md](control.md) | `/ws/control/<uuid>` | Machine control: files, play, config, firmware, raw mode | `helpers/api/control.ts` |
| [camera.md](camera.md) | `/ws/camera/<uuid>` | Camera frame streaming (+ fisheye correction) | `helpers/api/camera.ts` |
| [camera-calibration.md](camera-calibration.md) | `/ws/camera-calibration` | Chessboard/charuco/fisheye calibration solving | `helpers/api/camera-calibration.ts` |
| [camera-transform.md](camera-transform.md) | `/ws/camera-transform` | Apply calibration transforms to images | `helpers/api/camera-transform.ts` |
| [svgeditor-laser-parser.md](svgeditor-laser-parser.md) | `/ws/svgeditor-laser-parser` | SVG scene → gcode/FCode toolpath generation | `helpers/api/svg-laser-parser.ts` |
| [utils.md](utils.md) | `/ws/utils` | pdf2svg, color split, contour matching, misc | `helpers/api/utils-ws.ts` |
| [opencv.md](opencv.md) | `/ws/opencv` | Image sharpening (OpenCV) | `helpers/api/open-cv.ts` |
| [push-studio.md](push-studio.md) | `/ws/push-studio` | Push channel: Illustrator plugin → Beam Studio | `helpers/api/ai-extension.ts` |
| [inter-process.md](inter-process.md) | `/ws/inter-process` | Inbound relay from the Illustrator plugin (external caller) | none (external) |
| [ver.md](ver.md) | `/ws/ver` | One-shot version probe, closes after push | none (manual smoke tests) |
| [device-manager.md](device-manager.md) | `/ws/device-manager/<uuid>` | Device settings sessions | none — legacy |
| [usb-config.md](usb-config.md) | `/ws/usb-config` | UART device setup | none — legacy |
| [usb-interfaces.md](usb-interfaces.md) | `/ws/usb/interfaces` | h2h USB enumeration (gates `/usb/<addr>` routes) | none — legacy |
| [image-tracer.md](image-tracer.md) | `/ws/image-tracer` | Raster → SVG tracing | none — frontend uses `imagetracerjs` |

## Shared Protocol Conventions

- Text frames are JSON with a `status` field: `ok`, `error` (recoverable, with `error` symbol), `fatal` (socket closes), `connecting`/`connected` (machine link phase), `continue` (send binary now), `binary` (binary frames follow), `progress`/`uploading`/`transfer`/`computing` (long ops), `complete`, `pong`. Helpers: [`fluxghost/api/api_base.py`](../../fluxghost/api/api_base.py).
- Binary uploads: command with a byte size → `{"status": "continue"}` → client streams chunks → reassembled by `BinaryUploadHelper` ([`fluxghost/api/misc.py`](../../fluxghost/api/misc.py)) → `ok`.
- Endpoints that open a machine session (`control`, `camera`, `device-manager`) expect the client's **RSA public key PEM as the first text message**; `touch` takes it as a JSON field.
- Idle connections are closed after 600 s ([`fluxghost/websocket/base.py`](../../fluxghost/websocket/base.py)); Beam Studio pings every 60 s.

## Maintenance Rules

- These docs are the protocol source of truth (the GitHub wiki is stale; wrapper docstrings in `fluxghost/websocket/*.py` contain known errors). If you change an endpoint's behavior, update its doc **in the same change**.
- Every claim here was written from the handler source with `file:line` citations on 2026-07-05. If code and doc disagree, the code wins — fix the doc and re-verify with `uv run python tools/ws_smoke.py`.

## Testing Against a Simulated Device

Start the backend with `-d` to register a fake device (uuid `00000000000000000000000000000000`, name "Simulate Device"):

```sh
uv run ghost.py -d --port 8000
```

Verified working against the simulator (2026-07-05): `discover` announces it, `touch` authorizes it (any key), `control` connects and serves `file ls SD` / `play report`, and `camera` streams PNG frames at 4 fps. `svgeditor-laser-parser` and the image endpoints need no device at all.
