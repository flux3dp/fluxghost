
from getpass import getuser
from shlex import split
from uuid import UUID
import logging
import socket

from fluxclient.device.host2host_usb import FluxUSBError
from fluxclient.device.manager import (DeviceManager, ManagerError,
                                       ManagerException)
from fluxclient.encryptor import KeyObject
from fluxghost import g

logger = logging.getLogger("API.CONTROL_BASE")

STAGE_DISCOVER = '{"status": "connecting", "stage": "discover"}'
STAGE_CONNECTIONG = '{"status": "connecting", "stage": "connecting"}'
STAGE_REQUIRE_AUTHORIZE = '{"status": "req_authorize", "stage": "connecting"}'
STAGE_TIMEOUT = '{"status": "error", "error": "TIMEOUT"}'


def manager_mixin(cls):
    class ManagerAPI(cls):
        target = None
        manager = None
        client_key = None

        def __init__(self, *args, **kw):
            super().__init__(*args)
            if "uuid" in kw:
                self.target = ("uuid", UUID(hex=kw["uuid"]))
            elif "usb_addr" in kw:
                self.target = ("h2h", int(kw["usb_addr"]))
            elif "uart" in kw:
                self.target = ("uart", kw["uart"])
            else:
                raise SystemError("Poor connection configuration")
            self.POOL_TIME = 1.5

        def on_connected(self):
            import json
            payload = {"status": "connected",
                       "serial": self.manager.serial,
                       "version": str(self.manager.version),
                       "model": self.manager.model_id,
                       "name": self.manager.nickname}
            self.send_text(json.dumps(payload))

        def try_connect(self):
            self.send_text(STAGE_DISCOVER)
            endpoint_type, endpoint_target = self.target

            if endpoint_type == "uuid":
                if endpoint_target in self.server.discover_devices:
                    device = self.server.discover_devices[endpoint_target]
                    self.send_text(STAGE_CONNECTIONG)

                    try:
                        self.manager = device.manage_device(self.client_key)

                    except (OSError, ConnectionError, socket.timeout) as e:  # noqa
                        logger.error("Socket erorr: %s", e)
                        self.send_fatal("DISCONNECTED")
                        return
                else:
                    self.send_fatal("NOT_FOUND")
                    return

            elif endpoint_type == "h2h":
                usbprotocol = g.USBDEVS.get(endpoint_target)
                self.send_text(STAGE_CONNECTIONG)

                if usbprotocol:
                    try:
                        self.manager = DeviceManager.from_usb(self.client_key,
                                                              usbprotocol)
                    except FluxUSBError:
                        logger.exception("USB control open failed.")
                        usbprotocol.stop()
                        raise RuntimeError("PROTOCOL_ERROR")
                else:
                    logger.debug(
                        "Try to connect to unknown device (addr=%s)",
                        self.target[1])
                    raise RuntimeError("UNKNOWN_DEVICE")
            elif endpoint_type == "uart":
                self.manager = DeviceManager.from_uart(self.client_key,
                                                       endpoint_target)
            else:
                self.send_fatal("UNKNOWN_ENDPOINT_TYPE", endpoint_type)
                return

            if self.manager.authorized:
                self.on_connected()
            else:
                self.send_text(STAGE_REQUIRE_AUTHORIZE)
            self.POOL_TIME = 30.0

        def on_text_message(self, message):
            if self.client_key:
                if self.manager.authorized:
                    self.on_command(*split(message))
                else:
                    if message.startswith("password "):
                        try:
                            self.manager.authorize_with_password(message[9:])
                            self.on_connected()
                        except (ManagerError, ManagerException) as e:
                            self.send_fatal(" ".join(e.err_symbol))
                    else:
                        self.send_text(STAGE_REQUIRE_AUTHORIZE)
            else:
                try:
                    self.client_key = KeyObject.load_keyobj(message)
                except ValueError:
                    self.send_fatal("BAD_PARAMS")
                    return
                except Exception:
                    logger.error("RSA Key load error: %s", message)
                    self.send_fatal("BAD_PARAMS")
                    raise

                try:
                    self.try_connect()
                except (ManagerException, ManagerError) as e:
                    self.send_fatal(" ".join(e.err_symbol))
                except RuntimeError as e:
                    self.send_fatal(e.args[0])
                except Exception:
                    logger.exception("Error while manager connecting")
                    self.send_fatal("L_UNKNOWN_ERROR")

        def on_binary_message(self, buf):
            self.send_fatal("PROTOCOL_ERROR",
                            "Can not accept binary data")

        def on_command(self, cmd, *args):
            fn_name = "cmd_" + cmd
            function = getattr(self, fn_name, self.cmd_not_found)
            try:
                function(*args)
            except ManagerError as e:
                self.send_error("", symbol=e.err_symbol)
            except RuntimeError as e:
                self.send_error("", symbol=e.args)
            except ManagerException as e:
                logger.exception("Device manager crashed")
                self.send_fatal(symbol=e.err_symbol)
            except Exception:
                logger.exception("Device manager crashed")
                self.send_fatal("L_UNKNOWN_ERROR")

        def cmd_list_trust(self, *args):
            self.send_ok(acl=self.manager.list_trust())

        def cmd_add_trust(self, pem, label=getuser(), *args):
            if pem == "self":
                pem = self.client_key.public_key_pem
            self.manager.add_trust(label, pem)
            self.send_ok()

        def cmd_remove_trust(self, access_id, *args):
            self.manager.remove_trust(access_id)
            self.send_ok()

        def cmd_set_nickname(self, nickname, *args):
            self.manager.set_nickname(nickname)
            self.send_ok()

        def cmd_reset_password(self, new_password):
            self.manager.reset_password(new_password)
            self.send_ok()

        def cmd_set_password(self, old_password, new_password, *args):
            reset_acl = "reset_acl" in args
            self.manager.set_password(old_password, new_password, reset_acl)
            self.send_ok()

        def cmd_set_network(self, *args):
            options = {}
            for arg in args:
                kv = arg.split("=", 1)
                if len(kv) == 2:
                    k, v = kv
                    options[k] = v
            self.manager.set_network(**options)
            self.send_ok()

        def cmd_scan_wifi_access_points(self, *args):
            self.send_ok(access_points=self.manager.scan_wifi_access_points())

        def cmd_get_wifi_ssid(self, *args):
            self.send_ok(ssid=self.manager.get_wifi_ssid())

        def cmd_get_ipaddr(self, *args):
            self.send_ok(ipaddrs=self.manager.get_ipaddr())

        def cmd_not_found(self, *args):
            self.send_error("", symbol=("L_UNKNOWN_COMMAND", ))

        def on_closed(self):
            if self.manager:
                self.manager.close()
                self.manager = None

    return ManagerAPI
