# Inter Process

`ws://127.0.0.1:<port>/ws/inter-process`

Inbound bridge for an external process (in practice the Adobe Illustrator plugin — the
only command is literally `adobe_illustrator`) to push an SVG plus layer settings into
Beam Studio. The payload is relayed to whichever websocket registered itself on
[`/ws/push-studio`](push-studio.md); this endpoint stores nothing itself.

- **Handler**: `fluxghost/api/inter_process.py` (`inter_process_api_mixin`), wrapped by
  `fluxghost/websocket/inter_process.py` (`WebsocketInterProcess`), routed in
  `fluxghost/http_websocket_route.py` (`inter-process`).
- **Beam Studio client**: none found (no reference to `inter-process` under
  `beam-studio/packages/core/src/web`). The client is an external process; it receives
  the relayed data indirectly through Beam Studio's push-studio client
  (`packages/core/src/web/helpers/api/ai-extension.ts`).

## Connection

Standard fluxghost websocket upgrade; nothing is sent on connect. Non-localhost
`Origin` headers are rejected unless the server runs with `--allow-foreign`
(`fluxghost/http_handler.py`). The handler keeps the `HttpServer` instance as
`self.http_handler` (constructor arg `args[2]`) purely to reach
`http_handler.push_studio_ws` — the shared slot set by `/ws/push-studio`'s
`set_handler` command (`fluxghost/http_server_base.py`).

External processes can discover the port from the `FluxStudioPort` file that fluxghost
writes to the platform app-data directory when started with `--port 0`
(`fluxghost/http_server_base.py`).

## Commands / Message Flow

### `connect`

Handshake/liveness check. Any parameters are ignored.

```
→ connect
← {"type": "connect", "status": "ok"}
```

### `adobe_illustrator <file_length> <layerData>`

Announce an SVG upload. The params are split on spaces: `message[0]` is the byte
length of the upcoming binary payload, `message[1]` is an opaque string forwarded
verbatim as `layerData` (Beam Studio parses it as JSON, so it must contain no spaces —
anything after the second token is dropped by the split).

```
→ adobe_illustrator 1024 {"Layer1":{"name":"Layer1","power":"50","speed":"30"}}
← {"status": "continue"}
→ <binary frames totalling exactly 1024 bytes>
```

Once exactly `file_length` bytes have arrived (`BinaryUploadHelper` in
`fluxghost/api/misc.py`), the buffer is decoded as UTF-8 and pushed to the registered
push-studio socket via `push_studio_ws.send_ok(svg=svg, layerData=message[1])`:

```
(on /ws/push-studio) ← {"svg": "<svg ...>", "layerData": "{...}", "status": "ok"}
```

**No confirmation is sent back on this socket** — the only responses the publisher
ever sees are `{"type": "connect", "status": "ok"}` and `{"status": "continue"}`.

## Errors

- Unknown command → `{"status": "Error", "message": "BAD_PARAM_TYPE"}`
  (`OnTextMessageMixin`). Non-integer `file_length` also raises `ValueError` and
  produces the same message.
- Text frame while the binary upload is in progress →
  `{"status": "fatal", "symbol": ["PROTOCOL_ERROR"], "error": "PROTOCOL_ERROR"}`,
  connection closed.
- Binary frame without a preceding `adobe_illustrator` →
  `{"status": "fatal", "symbol": ["BAD_PROTOCOL"], "error": "BAD_PROTOCOL"}`, closed.
- More bytes than `file_length` → `BinaryUploadHelper.feed` raises `BAD_LENGTH ...`,
  surfaced as `{"status": "fatal", ...}`, closed.
- No binary data for 60 s during an upload →
  `{"status": "fatal", "symbol": ["TIMEOUT", "WAITING_BINARY"], "error": "TIMEOUT",
  "info": "WAITING_BINARY"}`, closed (`WebSocketBase.check_ttl`).
- **No push-studio handler registered** (`push_studio_ws` is `None`, its initial value)
  → the relay callback raises `AttributeError`, which nothing catches except the
  top-level `except Exception` in `WebSocketBase.serve_forever`; the inter-process
  connection is closed with no error message sent.
- Idle for more than 600 s → socket closed with close message `error TIMEOUT`.

## Example Session

```
→ connect
← {"type": "connect", "status": "ok"}
→ adobe_illustrator 2048 {"Layer1":{"name":"Layer1","power":"50","speed":"30"}}
← {"status": "continue"}
→ <2048 bytes of SVG, in one or more binary frames>

# nothing more arrives here; simultaneously on /ws/push-studio:
← {"svg": "<svg ...>...</svg>",
   "layerData": "{\"Layer1\":{\"name\":\"Layer1\",\"power\":\"50\",\"speed\":\"30\"}}",
   "status": "ok"}
```

## Notes

- **Relationship to push-studio**: the two endpoints form a one-way, one-slot message
  bus over the shared `HttpServer.push_studio_ws` attribute. `/ws/inter-process` is the
  publisher (Illustrator plugin), `/ws/push-studio` the subscriber (the focused Beam
  Studio tab). Verified in code: `fluxghost/api/inter_process.py` line 26 writes to the
  socket stored by `fluxghost/api/push_studio.py` line 18.
- The attribute name `self.http_handler` is misleading — the constructor's third
  argument is the `HttpServer` instance (see `ws_class(self.request, client,
  self.server, self.path, **kwargs)` in `fluxghost/http_handler.py`), the same object
  `push_studio.py` calls `self.server`.
- The wrapper docstring in `fluxghost/websocket/inter_process.py` shows
  `/ws/inter_process` (underscore); the actual route regex is `inter-process`.
