# Discover

`ws://127.0.0.1:8000/ws/discover`

Server-push endpoint that periodically broadcasts the presence (and disappearance) of FLUX devices found on the local network. The client can also send "poke" commands to actively probe specific IP addresses.

- **Handler**: `fluxghost/api/discover.py` (mixin), wrapper `fluxghost/websocket/discover.py`
- **Beam Studio client**: `packages/core/src/web/helpers/api/discover.ts` (`DiscoverManager`)

## Connection

No URL parameters and no authentication (the server rejects websocket upgrades with a non-localhost `Origin` header unless started with `--allow-foreign`, `fluxghost/http_handler.py:156-163`). On open the server immediately starts its review loop: every poll cycle it walks `self.server.discover_devices` and pushes one JSON message per device (`fluxghost/api/discover.py:67`). The poll interval starts at 1.0 s and grows by 1.0 s per loop up to a cap of 3.0 s (`fluxghost/api/discover.py:135-137`).

A device is considered dead when its `last_update` is older than 30 seconds (`fluxghost/api/discover.py:72`); a dead message is sent once, when the device transitions from alive to dead. Alive devices are re-broadcast on **every** loop, so the client receives each online device roughly every 1–3 seconds.

USB (`h2h`) review exists in the code but is disabled — `review_usb_devices()` is commented out in `on_review_devices()` (`fluxghost/api/discover.py:99-101`), so in practice only `source: "lan"` messages are pushed.

## Commands

All commands are JSON text messages of the form `{"cmd": "...", "ipaddr": "..."}` (`fluxghost/api/discover.py:103`). None of them produce a direct reply; they trigger UDP/TCP probes whose results surface later as regular device-push messages. `OSError` from a probe is silently swallowed.

### `poke`

```
→ {"cmd": "poke", "ipaddr": "192.168.1.100"}
```

Sends a UDP discovery poke to the address via `self.server.discover.poke(ipaddr)` (`fluxghost/api/discover.py:111-117`).

### `poketcp`

```
→ {"cmd": "poketcp", "ipaddr": "192.168.1.100"}
```

Adds the address to the TCP poke list via `add_poketcp_ipaddr` (`fluxghost/api/discover.py:118-124`).

### `testtcp`

```
→ {"cmd": "testtcp", "ipaddr": "192.168.1.100"}
```

One-shot TCP reachability test with a 0.5 s timeout via `test_poketcp_ipaddr(ipaddr, 0.5)` (`fluxghost/api/discover.py:125-131`).

### Push message: device online

Built by `get_online_message()` (`fluxghost/api/discover.py:11-51`). For `source: "lan"`:

```json
{
  "uuid": "0123456789abcdef0123456789abcdef",
  "alive": true,
  "source": "lan",
  "serial": "F1XXXXXX",
  "version": "4.3.5",
  "model": "fbb1b",
  "name": "My Beambox",
  "ipaddr": "192.168.1.100",
  "password": false,
  "st_ts": 1234567,
  "st_id": 0,
  "st_prog": 0.0,
  "head_module": "LASER",
  "error_label": null
}
```

`password` is `device.has_password` (whether the machine is password-protected). The five `st_*`/status fields come from `device.status`; `head_module` falls back `st_head` → `head_module`, `error_label` falls back `st_err` → `error_label` (`fluxghost/api/discover.py:42-50`). The disabled `h2h` source would instead carry `name` (nickname) and `addr` fields.

### Push message: device offline

Built by `get_offline_message()` (`fluxghost/api/discover.py:54-55`):

```json
{"uuid": "0123456789abcdef0123456789abcdef", "alive": false, "source": "lan"}
```

## Errors

- Unparseable JSON → the server sends the **plain text** frame `BAD_PARAMS` (not JSON) (`fluxghost/api/discover.py:107`).
- Unknown `cmd` → `{"status": "error", "error": ["L_UNKNOWN_COMMAND"]}` via `send_error` (`fluxghost/api/discover.py:133`, `fluxghost/api/api_base.py:58`).
- Probe failures (`OSError`) are logged/ignored; no error is sent to the client.

## Example Session

```
→ {"cmd": "poke", "ipaddr": "192.168.1.100"}
→ {"cmd": "testtcp", "ipaddr": "192.168.1.100"}
→ {"cmd": "poketcp", "ipaddr": "192.168.1.100"}
← {"uuid": "0123...cdef", "alive": true, "source": "lan", "serial": "F1XXXXXX",
   "version": "4.3.5", "model": "fbb1b", "name": "My Beambox",
   "ipaddr": "192.168.1.100", "password": false, "st_ts": 1234567,
   "st_id": 0, "st_prog": 0.0, "head_module": "LASER", "error_label": null}
← ... (same message repeats every 1–3 s while the device is alive)
← {"uuid": "0123...cdef", "alive": false, "source": "lan"}     (30 s after last mDNS/UDP update)
```

## Notes

- The connection is long-lived and never closed by the handler; the generic websocket idle timeout is 600 s (`fluxghost/websocket/base.py:13`), but the constant push traffic never lets it trigger from the server side.
- Beam Studio keeps exactly one master `DiscoverManager` connected (web client, or one Electron tab); other tabs receive device lists over IPC (`discover.ts:61-127`).
- The frontend treats every incoming message as a device object: `alive: true` upserts into its device map, `alive: false` deletes (`discover.ts:170-187`). It independently expires devices after 15 s without an alive message (`CLEAR_DEVICES_INTERVAL`, `discover.ts:24`), tighter than the backend's 30 s.
- Beam Studio's `poke(ip)` sends up to three commands per call: always `poke`; plus `testtcp` and (unless `isTesting`) `poketcp` when `withTcp` is true, the default (`discover.ts:312-328`). It round-robins through its stored `poke-ip-addr` list every 1 s (`discover.ts:261-270`) and auto-appends the IP of every device it sees (max 20 entries).
- The frontend never sends any other command and has no handler for the `BAD_PARAMS` / `L_UNKNOWN_COMMAND` responses — they would be passed to `onMessage` like a device record.
