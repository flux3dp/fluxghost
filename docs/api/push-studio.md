# Push Studio

`ws://127.0.0.1:<port>/ws/push-studio`

Registers a Beam Studio window as the receiver of content pushed from an external
process (the Adobe Illustrator "AI extension" plugin). The endpoint itself accepts a
single command; the actual payloads (SVG + layer settings) are pushed to it by the
[`/ws/inter-process`](inter-process.md) endpoint.

- **Handler**: `fluxghost/api/push_studio.py` (`push_studio_api_mixin`), wrapped by
  `fluxghost/websocket/push_studio.py` (`WebsocketPushStudio`), routed in
  `fluxghost/http_websocket_route.py` (`push-studio`).
- **Beam Studio client**: `packages/core/src/web/helpers/api/ai-extension.ts`
  (initialized once at startup from `app/actions/beambox/beambox-init.ts`).

## Connection

Standard fluxghost websocket upgrade. Nothing is sent by the server on connect.
Connections with a non-localhost `Origin` are rejected with HTTP 404 unless the server
runs with `--allow-foreign` (`fluxghost/http_handler.py`, `serve_websocket`).

The handler keeps a reference to the `HttpServer` instance (`self.server = args[2]`);
calling `set_handler` stores this websocket on the server as `server.push_studio_ws`
(`fluxghost/http_server_base.py`, `set_push_studio_ws`). There is only **one** slot —
the most recent `set_handler` from any connection wins. Beam Studio uses this in its
multi-tab Electron app: each tab connects, and a tab re-sends `set_handler` whenever it
gains focus (`tabController.onFocused` in `ai-extension.ts`), so pushed content always
lands in the focused tab.

## Commands / Message Flow

### `set_handler`

Register this connection as the push target. Any text after the command is ignored.

```
→ set_handler
← {"cmd": "set_handler", "status": "ok"}
```

### Pushed messages (server → client, unsolicited)

When an Illustrator export completes on `/ws/inter-process`, its callback calls
`push_studio_ws.send_ok(svg=svg, layerData=...)` (`fluxghost/api/inter_process.py`),
so the registered client receives:

```
← {"svg": "<svg ...>...</svg>", "layerData": "<JSON string>", "status": "ok"}
```

- `svg` — the uploaded file decoded as UTF-8 text.
- `layerData` — a JSON **string** (not object). Beam Studio parses it as
  `Record<string, { name: string; power: string; speed: string }>` and, after importing
  the SVG as a layer, writes `speed`/`power` (parsed with `parseInt`) onto each named
  layer (`ai-extension.ts`, `onMessage`).

## Errors

- Unknown command → `{"status": "Error", "message": "BAD_PARAM_TYPE"}` (note the
  capitalized `Error`; from `OnTextMessageMixin` in `fluxghost/api/misc.py`).
- Binary frame sent (no binary upload is ever expected here) →
  `{"status": "fatal", "symbol": ["BAD_PROTOCOL"], "error": "BAD_PROTOCOL"}` and the
  connection is closed (`BinaryHelperMixin.on_binary_message` + `WebSocketBase.send_fatal`).
- Idle for more than 600 s (`WebSocketBase.TIMEOUT`) → server closes the socket with
  close message `error TIMEOUT`.

Beam Studio's generic websocket helper (`helpers/websocket.ts`) routes
`status: "error"` to `onError` and `status: "fatal"` to `onFatal`; both just
`console.log` in `ai-extension.ts`. Everything else (including the pushed
`status: "ok"` payload) goes to `onMessage`.

## Example Session

```
# Beam Studio tab connects and takes the handler slot
→ set_handler
← {"cmd": "set_handler", "status": "ok"}

# ...later, an Illustrator plugin finishes an upload on /ws/inter-process...
← {"svg": "<svg xmlns=\"http://www.w3.org/2000/svg\">...</svg>",
   "layerData": "{\"Layer1\":{\"name\":\"Layer1\",\"power\":\"50\",\"speed\":\"30\"}}",
   "status": "ok"}
```

## Notes

- This endpoint is a pure receiver/registration socket: `set_handler` is the only
  command in `cmd_mapping`; all real data arrives unsolicited via the shared
  `server.push_studio_ws` reference used by `/ws/inter-process`.
- The handler slot is never cleared on disconnect — if the registered socket has
  closed and no other tab re-registers, a subsequent inter-process push raises an
  unhandled exception on the *inter-process* connection (see that doc's Errors).
- The wrapper docstring in `fluxghost/websocket/push_studio.py` shows the route as
  `ws://127.0.0.1:8000/ws/push_studio`, but the actual route regex is `push-studio`
  (hyphen) in `fluxghost/http_websocket_route.py`.
