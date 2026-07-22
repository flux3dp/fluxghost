# Device Manager

`ws://127.0.0.1:8000/ws/device-manager/<uuid>`

Opens a management session to a single machine for configuration tasks — trust list (ACL), nickname, password, and network setup — over network, host-to-host USB, or a UART serial port. It is the "settings" counterpart to the `control` endpoint.

- **Handler**: `fluxghost/api/device_manager.py` (`manager_mixin`), wrapper `fluxghost/websocket/device_manager.py` - **Beam Studio client**: none found (no reference to `device-manager` anywhere under `packages/core/src/web`)

## Connection

Three route variants select the transport (`fluxghost/http_websocket_route.py:7-15`):

| URL | Target |
| --- | --- |
| `/ws/device-manager/<uuid>` (32 hex chars) | Network device previously seen by the `discover` endpoint |
| `/ws/device-manager/usb/<addr>` (1–3 digits) | Host-to-host USB device, by the address **already opened** via `/ws/usb/interfaces` (`g.USBDEVS`) |
| `/ws/device-manager/uart/<path>` | UART serial port, e.g. `/dev/ttyUSB0` (`DeviceManager.from_uart`) |

An unrecognized combination of kwargs raises `SystemError('Poor connection configuration')` (`device_manager.py:34-35`).

The server sends nothing on open. The **first text message must be the client's RSA key in PEM format** (`KeyObject.load_keyobj`, `device_manager.py:118-127`); a bad key gets `status: fatal` with `BAD_PARAMS`. On a valid key the server immediately tries to connect (`try_connect`, `device_manager.py:48-92`), streaming stage messages:

1. `{"status": "connecting", "stage": "discover"}` — always.
2. `{"status": "connecting", "stage": "connecting"}` — uuid and usb variants only (not uart).
3. Then either, if the machine already trusts the key:
   ```json
   {"status": "connected", "serial": "...", "version": "...", "model": "...", "name": "..."}
   ```
   or, if authorization is required:
   ```json
   {"status": "req_authorize", "stage": "connecting"}
   ```

While unauthorized, the only accepted message is `password <password>` (`device_manager.py:110-117`). Success produces the `connected` payload above; a `ManagerError` becomes a fatal close with the joined `err_symbol`. Any other message just re-sends `req_authorize`.

## Commands

Available once `connected`. Messages are tokenized with `shlex.split`, so quote arguments containing spaces (`device_manager.py:94-108`). Unless noted, success is `{"status": "ok"}`.

### `list_trust`
Lists the machine's trusted-key ACL (`device_manager.py:160-161`).
`← {"status": "ok", "acl": [...]}`

### `add_trust <pem|self> [label]`
Adds a public key to the trust list (`device_manager.py:163-169`). `self` substitutes the session key's `public_key_pem`; `label` defaults to the local OS username (`fluxghost/utils/username.py`).

### `remove_trust <access_id>`
Removes an ACL entry by access id (`device_manager.py:171-173`).

### `set_nickname <nickname>`
Renames the machine. Matched as a **raw prefix** before shlex parsing, so everything after `set_nickname ` (including spaces) is the nickname (`device_manager.py:102-106`).

### `reset_password <new_password>`
Resets the password without knowing the old one (`device_manager.py:179-181`).

### `set_password <old_password> <new_password> [reset_acl]`
Changes the password; passing the literal token `reset_acl` also clears the trust list (`device_manager.py:183-186`).

### `set_network key=value ...`
Configures networking; each `key=value` token becomes a keyword argument to `manager.set_network` (`device_manager.py:188-196`), e.g. `set_network ssid=MyWifi psk=secret method=dhcp`.

### `set_network2 <json>`
Legacy raw-prefix variant: the remainder is a JSON object converted to `key=value` pairs and fed to `set_network` (`device_manager.py:97-101, 198-203`). Exceptions here are only logged — no error response is sent.

### `scan_wifi_access_points`
`← {"status": "ok", "access_points": [...], "cmd": "scan"}` (`device_manager.py:205-206`)

### `get_wifi_ssid`
`← {"status": "ok", "ssid": "..."}` (`device_manager.py:208-209`)

### `get_ipaddr`
`← {"status": "ok", "ipaddrs": [...]}` (`device_manager.py:211-212`)

### `get_network_status`
`← {"status": "ok", "ipaddr": [...], "ssid": "..."}` — note the singular `ipaddr` key here vs `ipaddrs` above (`device_manager.py:214-215`).

## Errors

- Unknown command → `{"status": "error", "error": ["L_UNKNOWN_COMMAND"]}` (`device_manager.py:217-218`).
- During a command (`on_command`, `device_manager.py:142-158`): `ManagerError` → `{"status": "error", "error": [<err_symbol...>]}`; `FluxUSBError` → error with its `symbol`; `RuntimeError` → error with its args. `ManagerException` or any other exception → **fatal** (socket closes): `ManagerException` uses its `err_symbol`, anything else `L_UNKNOWN_ERROR`.
- During connect (`device_manager.py:129-137`): fatal with `NOT_FOUND` (uuid not in discovered devices), `DISCONNECTED` (socket error to a network device), `UNKNOWN_DEVICE` (usb address not opened via `/ws/usb/interfaces`), `PROTOCOL_ERROR` (USB open failed; the USB daemon is stopped), the joined `err_symbol` of a `ManagerError`/`ManagerException`, or `L_UNKNOWN_ERROR`.
- Bad RSA key → fatal `BAD_PARAMS`; wrong password → fatal with the manager's error symbol (`device_manager.py:110-127`).
- Binary frames → fatal `{"status": "fatal", "symbol": ["PROTOCOL_ERROR", "Can not accept binary data"], "error": "PROTOCOL_ERROR", "info": "Can not accept binary data"}` (`device_manager.py:139-140`).

Fatal responses always close the websocket (`fluxghost/websocket/base.py:45-47`).

## Example Session

```
(connect to ws://127.0.0.1:8000/ws/device-manager/0123456789abcdef0123456789abcdef)
→ -----BEGIN RSA PRIVATE KEY-----\nMIICXAIBAAKBgQ...\n-----END RSA PRIVATE KEY-----
← {"status": "connecting", "stage": "discover"}
← {"status": "connecting", "stage": "connecting"}
← {"status": "req_authorize", "stage": "connecting"}
→ password flux
← {"status": "connected", "serial": "F1K23456", "version": "3.3.0", "model": "beambox", "name": "My Beambox"}
→ list_trust
← {"status": "ok", "acl": [{"access_id": "...", "label": "simon"}]}
→ add_trust self
← {"status": "ok"}
→ set_network ssid=MyWifi security=WPA2-PSK psk=secret method=dhcp
← {"status": "ok"}
→ get_network_status
← {"status": "ok", "ipaddr": ["192.168.1.50"], "ssid": "MyWifi"}
```

## Notes

- No consumer was found in Beam Studio (`packages/core/src/web`); this endpoint appears to be a legacy of the pre-Beam-Studio FLUX Studio device-settings flow. The modern network-setup path in Beam Studio does not go through fluxghost.
- The `usb/<addr>` variant only works after `open <addr>` on `/ws/usb/interfaces` has registered the address in `g.USBDEVS` (`device_manager.py:68-81`); otherwise the connect attempt is fatal `UNKNOWN_DEVICE`.
- The select-loop poll interval starts at 1.5 s and is relaxed to 30 s once the connect attempt finishes (`device_manager.py:36, 92`).
- The machine-side manager session is closed when the websocket closes (`on_closed`, `device_manager.py:220-223`).
- `STAGE_TIMEOUT` (`device_manager.py:17`) is defined but never sent.
- All the actual device I/O is delegated to `fluxclient.device.manager.DeviceManager`; the `acl`, `access_points`, `ssid`, and `ipaddrs` payload shapes come from that library.
