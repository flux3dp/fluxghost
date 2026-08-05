# Ver

`ws://127.0.0.1:8000/ws/ver`

Version/connectivity check: on connect the server immediately pushes the installed `fluxghost` and `fluxclient` versions and closes the socket. Useful as a one-shot "is the backend up?" probe.

- **Handler**: `fluxghost/api/ver.py` (mixin), wrapper `fluxghost/websocket/ver.py`
- **Beam Studio client**: none (no `Websocket({method: 'ver'})` usage in `packages/core/src/web`)

## Connection

No URL parameters, no authentication (localhost-only unless the server is started with `--allow-foreign`). Everything happens in the handler's constructor (`fluxghost/api/ver.py:7-10`): as soon as the websocket handshake completes, the server sends one JSON text frame and then closes the connection with a normal close frame. The client never needs to send anything.

## Commands

There are no commands. Any text or binary message a client manages to send before the close completes is ignored — the mixin defines no `on_text_message`/`on_binary_message`, and the connection is already closing.

### Push message: versions

Sent once, immediately on connect, via `send_json(fluxclient=..., fluxghost=...)` (`fluxghost/api/ver.py:9`, `fluxghost/api/api_base.py:37-41`):

```json
{"fluxclient": "2.10.3", "fluxghost": "2.5.6"}
```

- `fluxclient` — `fluxclient.__version__` of the bundled fluxclient library.
- `fluxghost` — `fluxghost.__version__` of the running backend.

Note there is no `status` field on this message, unlike most other fluxghost endpoints.

## Errors

None. The handler has no error paths of its own; the only failures a client can observe are transport-level (connection refused when the backend is not running, or the HTTP 404 the server returns for websocket upgrades whose `Origin` header is not `127.0.0.1`, `chrome-extension:`, or `file:` when `--allow-foreign` is off, `fluxghost/http_handler.py:156-163`).

## Example Session

```
   (client opens ws://127.0.0.1:8000/ws/ver)
← {"fluxclient": "2.10.3", "fluxghost": "2.5.6"}
   (server closes the websocket, normal closure)
```

## Notes

- The route regex is just `re.compile('ver')` matched against the path after `/ws/` (`fluxghost/http_websocket_route.py:22`), and matching is prefix-based (`re.match`), so any path starting with `ver` reaches this handler.
- Because the payload is sent from `__init__`, it is emitted during connection setup — before the serve loop runs — so the message and the close arrive essentially back-to-back.
- Beam Studio does not call this endpoint; it learns the backend port from the `{"type": "ready", "port": ...}` stdout line instead (see `fluxghost/http_server_base.py`). The endpoint is still handy for manual smoke tests, as suggested in the repo's CLAUDE.md.
- The same version pair is printed by `ghost.py --version` on the CLI.
