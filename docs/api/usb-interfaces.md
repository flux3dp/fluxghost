# USB Interfaces

`ws://127.0.0.1:8000/ws/usb/interfaces`

Enumerates FLUX host-to-host (h2h) USB devices and UART serial ports, and opens/closes the h2h USB link. Opening an address starts a background USB daemon and registers it in the process-global `g.USBDEVS`, which the `/usb/<addr>` variants of `device-manager`, `control`, and `camera` then attach to.

- **Handler**: `fluxghost/api/usb_interfaces.py` (`usb_interfaces_api_mixin`), wrapper `fluxghost/websocket/usb_interfaces.py` - **Beam Studio client**: none found (no reference to `usb/interfaces` anywhere under `packages/core/src/web`)

## Connection

No URL parameters and no auth handshake (`fluxghost/http_websocket_route.py:20`). The server sends nothing on open; it waits for text commands. State is global to the fluxghost process, not to this websocket: devices opened here stay open after the socket closes (`on_close` is a no-op, `usb_interfaces.py:78-79`).

## Commands

Dispatch in `on_text_message` (`usb_interfaces.py:65-73`). Messages that match no command are **silently ignored** (there is no unknown-command error).

### `list`
Enumerates both interface kinds (`list_devices`, `usb_interfaces.py:91-102`):

```json
{"status": "ok", "cmd": "list",
 "h2h": {"3": false, "5": {...device profile...}},
 "uart": ["/dev/tty.usbserial-1420"]}
```

- `h2h` — one entry per interface from `USBProtocol.get_interfaces()`, keyed by USB address. The value is the daemon's `endpoint_profile` object if that address is currently open, otherwise `false` (module docstring, `usb_interfaces.py:1-16`).
- `uart` — on macOS: `glob('/dev/tty.*')` minus anything containing `Bl`; elsewhere: `serial.tools.list_ports.comports()` entries whose hwid is not `n/a` (same logic as `usb-config`'s `list`).

### `open <addr>`
Opens the h2h device at the given integer address (`open_device`, `usb_interfaces.py:104-123`). On success it spawns a daemon thread running `USBProtocol.run()` and registers the protocol in `g.USBDEVS[addr]` (`h2h_usb_daemon_thread`, `usb_interfaces.py:44-54`):

```json
{"status": "ok", "cmd": "open", "devopen": 5, "profile": {...device profile...}}
```

### `close <addr>`
Stops the daemon for an opened address (`close_device`, `usb_interfaces.py:125-132`):

```json
{"status": "ok", "cmd": "close", "devclose": 5}
```

## Errors

All errors are `{"status": "error", "error": ["<SYMBOL>"], "cmd": "<open|close>"}`:

- `open` when the address is already open → `RESOURCE_BUSY` (`usb_interfaces.py:105-107`).
- `open` when no interface has that address → `NOT_FOUND` (`usb_interfaces.py:123`).
- `open` when the USB connect raises `FluxUSBError` → the exception's `symbol` (`usb_interfaces.py:120-121`). The module docstring (`usb_interfaces.py:25-28`) names the expected symbols: `TIMEOUT` (device no response), `UNAVAILABLE` (device occupied by another program), `UNKNOWN_ERROR`.
- `close` on an address that is not open → `NOT_FOUND` (`usb_interfaces.py:131-132`).

`list` has no error responses (docstring: "errors: n/a"). `open` with a non-numeric address raises `ValueError` in `int()` before any handler runs — no error frame is sent. Binary frames are ignored (`usb_interfaces.py:75-76`).

## Example Session

```
(connect to ws://127.0.0.1:8000/ws/usb/interfaces)
→ list
← {"status": "ok", "cmd": "list", "h2h": {"5": false}, "uart": ["/dev/tty.usbserial-1420"]}
→ open 5
← {"status": "ok", "cmd": "open", "devopen": 5, "profile": {"serial": "F1K23456", ...}}
→ list
← {"status": "ok", "cmd": "list", "h2h": {"5": {"serial": "F1K23456", ...}}, "uart": [...]}
   (client may now connect ws://127.0.0.1:8000/ws/device-manager/usb/5 or /ws/control/usb/5)
→ close 5
← {"status": "ok", "cmd": "close", "devclose": 5}
→ close 5
← {"status": "error", "error": ["NOT_FOUND"], "cmd": "close"}
```

## Notes

- No consumer was found in Beam Studio (`packages/core/src/web`); modern Beam Studio USB connectivity does not use the h2h protocol through fluxghost.
- This is the gatekeeper for every `/usb/<addr>` route: `device-manager/usb/<addr>` and `control|camera/usb/<addr>` look the address up in `g.USBDEVS` and fail (`UNKNOWN_DEVICE`) unless `open <addr>` succeeded here first.
- The daemon thread removes itself from `g.USBDEVS` and closes the protocol when `USBProtocol.run()` returns or crashes (`usb_interfaces.py:44-54`), so a device can disappear from `g.USBDEVS` without a `close` command.
- `get_devices` (`usb_interfaces.py:81-89`), which prunes `g.USBDEVS` to currently attached interfaces, is defined but never called.
- USB addresses are keys of a JSON object in `list` (hence strings on the wire) but integers in `open`/`close` responses.
- Device enumeration and the h2h protocol itself live in `fluxclient.device.host2host_usb.USBProtocol`.
