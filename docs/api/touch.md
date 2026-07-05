# Touch

`ws://127.0.0.1:8000/ws/touch`

Pairs the client with a discovered device: it authenticates against the machine (with or without a password) and registers the client's RSA public key on the machine's trust list, so later `control`/`camera` sessions can connect without a password.

- **Handler**: `fluxghost/api/touch.py` (mixin), wrapper `fluxghost/websocket/touch.py`
- **Beam Studio client**: `packages/core/src/web/helpers/api/touch.ts`

## Connection

No URL parameters and no auth to fluxghost itself (non-localhost `Origin` headers are rejected unless the server runs with `--allow-foreign`). The server sends nothing on open; it waits for a request message. The connection stays open across multiple requests (the frontend closes it after the first success).

## Commands

### Touch request (the only message)

A single JSON text message (`fluxghost/api/touch.py:18-25`):

```json
{
  "uuid": "0123456789abcdef0123456789abcdef",
  "key": "-----BEGIN RSA PRIVATE KEY-----\n...",
  "password": "machine-password"
}
```

- `uuid` (required) — device UUID hex from the discover endpoint.
- `key` (required) — an RSA key in PEM, loaded via `KeyObject.load_keyobj` (`fluxghost/api/touch.py:22`). Beam Studio sends its locally generated 1024-bit **private** key (`touch.ts:35`, `helpers/rsa-key.ts`); the backend derives the public key from it and registers `public_key_pem` on the device.
- `password` (optional) — machine password. If omitted/empty, the server only attempts key-based auth.

Flow in `touch_device()` (`fluxghost/api/touch.py:45-102`):

1. `uuid == 0` (all zeros) → immediately replies with a simulate-device success and returns:
   ```json
   {"serial": "SIMULATE00", "name": "Simulate Device", "has_response": true, "reachable": true, "auth": true}
   ```
2. Otherwise looks the device up in `server.discover_devices`; if not found, falls back to `DeviceManager.from_uuid(...)` with a 30 s `lookup_timeout` (`fluxghost/api/touch.py:61-67`).
3. If the management task is not already authorized: with a `password` it calls `task.authorize_with_password(password)`; without one it replies `auth: false` and stops.
4. On success it calls `task.add_trust(<local username>, <client public key PEM>)` (errors from an already-trusted key are suppressed, `fluxghost/api/touch.py:84-85`) and replies:

```json
{"uuid": "0123456789abcdef0123456789abcdef", "has_response": true, "reachable": true, "auth": true}
```

All non-simulate responses carry exactly the four fields `uuid`, `has_response`, `reachable`, `auth`.

## Errors

There is no `status: "error"` vocabulary here; failures are encoded in the boolean fields:

- Device unreachable (`OSError` during lookup/connect) → `{"uuid": ..., "has_response": false, "reachable": false, "auth": false}` (`fluxghost/api/touch.py:68-73`).
- Not authorized and no password given, or `ManagerError` with `AUTH_ERROR`/`TIMEOUT` (e.g. wrong password), or any other `ManagerError` → `{"uuid": ..., "has_response": true, "reachable": true, "auth": false}` (`fluxghost/api/touch.py:79-98`).
- `RuntimeError` → `{"uuid": ..., "has_response": false, "reachable": false, "auth": false}` (`fluxghost/api/touch.py:100-102`).
- Malformed request (bad JSON, missing `uuid`/`key`, bad key) → no response at all; the exception is logged and the websocket is **closed** (`fluxghost/api/touch.py:26-28`).

## Example Session

```
→ {"uuid": "0123456789abcdef0123456789abcdef",
   "key": "-----BEGIN RSA PRIVATE KEY-----\nMIICXAIBAAKBgQ...\n-----END RSA PRIVATE KEY-----",
   "password": "default"}
← {"uuid": "0123456789abcdef0123456789abcdef",
   "has_response": true, "reachable": true, "auth": true}
   (client closes the websocket)
```

Wrong password instead:

```
← {"uuid": "0123456789abcdef0123456789abcdef",
   "has_response": true, "reachable": true, "auth": false}
```

## Notes

- Beam Studio considers the touch successful only when `has_response`, `reachable`, and `auth` are all `true`; it then fires `onSuccess` and closes the socket, otherwise `onFail` with the same payload (`touch.ts:18-28`). It connects with `autoReconnect: false`.
- The frontend always sends a password: it defaults to the literal string `"default"` when none is supplied (`touch.ts:33`), so the backend's "no password → auth: false" branch is normally unreachable from Beam Studio.
- `_run_auth()` in `fluxghost/api/touch.py:30-43` (password auth with 3 timeout retries) is dead code — `touch_device()` never calls it.
- If the device was not seen by discover, the fallback `DeviceManager.from_uuid` lookup can block the handler for up to 30 s before a response arrives.
- Wrong-password and generic manager errors are indistinguishable to the client — both come back as `auth: false`.
