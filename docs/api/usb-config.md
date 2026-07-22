# USB Config

`ws://127.0.0.1:8000/ws/usb-config`

Configures a machine over a **UART serial port**: list serial ports, connect with an RSA key, then set nickname/password/network and read network status. Functionally a serial-only overlap of the `device-manager` endpoint, with a JSON-flavored command syntax.

- **Handler**: `fluxghost/api/usb_config.py` (`usb_config_api_mixin`), wrapper `fluxghost/websocket/usb_config.py` - **Beam Studio client**: none found (no reference to `usb-config` anywhere under `packages/core/src/web`)

## Connection

No URL parameters (`fluxghost/http_websocket_route.py:21`). The server sends nothing on open. The session holds one "task" (device connection) at a time, initialized to a `NoneTask` sentinel; any device command before a successful `connect` raises `RuntimeError('NOT_CONNECTED')` (`usb_config.py:150-152`), which surfaces as an `L_UNKNOWN_ERROR` traceback error (see Errors).

The wrapper docstring (`fluxghost/websocket/usb_config.py:5-19`) shows the intended JavaScript usage: open the socket, then `ws.send("list")`, `ws.send("connect /dev/ttyUSB0")`.

## Commands

Dispatch is by string prefix (`on_text_message`, `usb_config.py:97-122`).

### `list`
Lists candidate serial ports (`usb_config.py:24-31`). On macOS: `glob('/dev/tty.*')` minus anything containing `Bl` (Bluetooth); elsewhere: `serial.tools.list_ports.comports()` entries whose hwid is not `n/a`.
`← {"status": "ok", "ports": ["/dev/tty.usbserial-1420", ...]}`

### `key <pem>`
Loads the client RSA key (`KeyObject.load_keyobj`) used for the subsequent connect (`usb_config.py:101-104`).
`← {"status": "ok"}`

### `connect <port>`
Connects a `UartBackend(client_key, port)` to the given serial port (`usb_config.py:33-63`). Any previous task is closed first. Requires a prior `key` command, otherwise `{"status": "error", "error": ["KEY_ERROR"]}`.

```json
{"status": "ok", "cmd": "connect", "serial": "F1K23456", "version": "3.3.0",
 "name": "My Beambox", "model": "beambox", "password": true, "uuid": "0123456789abcdef0123456789abcdef"}
```

`password` is hard-coded `true`. The special port name `SIMULATE` selects the in-process `SimulateTask` (`usb_config.py:43-44`) — but see Notes.

### `auth` / `auth <password>`
Adds the client's public key to the machine's trust list under the label `DUMMY`; a `ManagerError` (e.g. already trusted) is suppressed (`usb_config.py:92-95`). The optional password argument is parsed but **ignored** — `auth()` never uses it.
`← {"status": "ok", "cmd": "auth"}`

### `set general <json>`
Sets the nickname from the JSON object's `name` field, e.g. `set general {"name": "My Beambox"}` (`usb_config.py:65-68`). Other fields are ignored.
`← {"status": "ok"}`

### `scan_wifi`
`← {"status": "ok", "cmd": "scan", "wifi": [...]}` — access points from `task.scan_wifi_access_points()` (`usb_config.py:77-79`).

### `set network <json>`
JSON object fields become keyword arguments to `task.set_network(**options)`, e.g. `set network {"ssid": "MyWifi", "security": "WPA2-PSK", "psk": "secret", "method": "dhcp"}` (`usb_config.py:81-84`).
`← {"status": "ok"}`

### `get network`
`← {"status": "ok", "cmd": "network", "ssid": "MyWifi", "ipaddr": ["192.168.1.50"]}` (`usb_config.py:86-90`)

### `set password <password>`
Calls `task.set_password('', password, True)` — empty old password, and the `True` resets the ACL (`usb_config.py:70-75`). If the backend returns `'OK'`: `{"status": "ok", "cmd": "password"}`; any other return value is sent as an error symbol.

## Errors

All commands share one handler (`usb_config.py:124-136`):

- Unknown command → `{"status": "error", "error": ["L_UNKNOWN_COMMAND"]}`.
- `ManagerException` (link-level failure) → `{"status": "error", "error": [<err_symbol...>], "info": "<str(e)>"}`, and the task is closed/reset to `NoneTask`.
- `ManagerError` (device replied with an error) → `{"status": "error", "error": [<e.args...>]}`.
- Anything else — including `NOT_CONNECTED` from using a command before `connect` — → `send_traceback('L_UNKNOWN_ERROR')`: `{"status": "error", "error": ["L_UNKNOWN_ERROR"], "traceback": [...]}` (`fluxghost/api/api_base.py:73-82`).
- `connect` without a key → `{"status": "error", "error": ["KEY_ERROR"]}` (`usb_config.py:39-41`).

Binary frames are silently ignored (`usb_config.py:138-139`). This endpoint never sends `status: fatal`.

## Example Session

```
(connect to ws://127.0.0.1:8000/ws/usb-config)
→ list
← {"status": "ok", "ports": ["/dev/tty.usbserial-1420"]}
→ key -----BEGIN RSA PRIVATE KEY-----\nMIICXAIBAAKBgQ...\n-----END RSA PRIVATE KEY-----
← {"status": "ok"}
→ connect /dev/tty.usbserial-1420
← {"status": "ok", "cmd": "connect", "serial": "F1K23456", "version": "3.3.0",
   "name": "My Beambox", "model": "beambox", "password": true,
   "uuid": "0123456789abcdef0123456789abcdef"}
→ auth
← {"status": "ok", "cmd": "auth"}
→ scan_wifi
← {"status": "ok", "cmd": "scan", "wifi": [{"ssid": "MyWifi", ...}]}
→ set network {"ssid": "MyWifi", "security": "WPA2-PSK", "psk": "secret", "method": "dhcp"}
← {"status": "ok"}
→ get network
← {"status": "ok", "cmd": "network", "ssid": "MyWifi", "ipaddr": ["192.168.1.50"]}
```

## Notes

- No consumer was found in Beam Studio (`packages/core/src/web`); this is a legacy endpoint from the Delta-era USB/UART setup flow.
- The `SIMULATE` port is effectively broken: `SimulateTask` (`usb_config.py:158-173`) defines `remote_version`/`name`/`model_id`/`serial` but the connect response reads `t.version`, `t.nickname`, and `t.uuid`, which don't exist — the resulting `AttributeError` resets the task and returns `L_UNKNOWN_ERROR`.
- A commented-out `UsbTask` alternative remains at `usb_config.py:49-50`; only `UartBackend` is live.
- `get network` is matched with `startswith`, so any suffix (e.g. `get network2`) triggers the same handler (`usb_config.py:117`).
- The task is closed when the websocket closes (`on_close`, `usb_config.py:141-145`).
- Serial-port I/O and the actual configuration protocol live in `fluxclient.device.manager_backends.UartBackend`.
