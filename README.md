# FLUXGhost

FLUXGhost is the local Python backend for [Beam Studio](https://github.com/flux3dp/beam-studio), FLUX's laser cutting/engraving software. It exposes a websocket API on `127.0.0.1:8000` (default) that the frontend uses for device discovery, machine control, camera streaming, calibration, and SVG → FCode toolpath generation. The machine layer is provided by [fluxclient](https://github.com/flux3dp/fluxclient-dev), with [fluxsvg](https://github.com/flux3dp/fluxsvg) and beamify handling SVG processing.

Supported machines: beamo, Beambox (Pro), HEXA, Ador, Beambox II, beamo II, HEXA II RF, and the UV printer series.

Official site: <https://flux3dp.com/>

## Documentation

| Doc | Contents |
|---|---|
| [docs/architecture.md](docs/architecture.md) | Server model, endpoint table, message protocol, Beam Studio integration |
| [docs/api/](docs/api/README.md) | Websocket API reference — one document per endpoint |
| [docs/todo.md](docs/todo.md) | Known issues, legacy candidates, cleanup backlog |
| [CLAUDE.md](CLAUDE.md) | Build/test/verify rules (written for AI coding agents, useful for humans too) |

## Quick Start (development)

Requires [uv](https://docs.astral.sh/uv/) (fetches the pinned Python 3.8 automatically) and sibling checkouts of the dependency repos:

```sh
# layout: fluxghost/, fluxclient-dev/, fluxsvg/, beamify/ side by side
cd fluxghost
uv sync
uv pip install ../fluxclient-dev ../beamify/python ../fluxsvg

# macOS (Apple Silicon): fluxsvg needs Homebrew cairo at runtime
brew install cairo
export DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib

# run the server
uv run ghost.py            # 127.0.0.1:8000
uv run ghost.py -d         # + registers a simulated device (no hardware needed)

# verify everything works (spawns its own server, 8 protocol checks)
uv run python tools/ws_smoke.py
```

## Docker

1. Install docker and docker compose.
2. Clone fluxclient-dev, beamify, and fluxsvg next to this repo.
3. Launch:

    ```sh
    docker compose build
    docker compose up -d
    ```

4. To shut down: `docker compose down`

## Compilation (for Beam Studio)

The desktop app bundles fluxghost as a PyInstaller binary:

```sh
uv sync --group deploy
uv run pyinstaller ghost.spec
```

Output lands in `./dist/ghost/` (`flux_api` executable). Beam Studio's `backend-manager.ts` spawns it with `--port 0` and reads the assigned port from the `{"type": "ready", "port": N}` stdout line.

---

## Legacy Notes (FLUX Delta era)

This project began as the backend for **FLUX Studio** and the **FLUX Delta** 3D printer — the original README described it as "a websocket based API for controlling your FLUX Delta". Some Delta-era surfaces still exist in the code (the `--slic3r`/`--cura` CLI flags, 3D-printing paths in fluxclient, scanner support) but are no longer maintained; current development is entirely laser-focused. Historical links:

* Official forum: <http://forum.flux3dp.com/>
* Legacy developer documentation: <http://dev.flux3dp.com/>
