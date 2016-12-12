
from io import BytesIO
from uuid import UUID
import logging
import socket

from fluxclient.robot.errors import RobotError, RobotSessionError
from fluxclient.robot.robot import FluxRobot
from fluxclient.utils.version import StrictVersion
from fluxclient.encryptor import KeyObject
from fluxghost import g

logger = logging.getLogger("API.CONTROL_BASE")

STAGE_DISCOVER = '{"status": "connecting", "stage": "discover"}'
STAGE_CONNECTIONG = '{"status": "connecting", "stage": "connecting"}'
STAGE_CONNECTED = '{"status": "connected"}'
STAGE_TIMEOUT = '{"status": "error", "error": "TIMEOUT"}'


def control_base_mixin(cls):
    class ControlBaseAPI(cls):
        uuid = None
        usb_addr = None

        binary_handler = None
        cmd_mapping = None
        client_key = None
        robot = None

        def __init__(self, *args, **kw):
            super().__init__(*args)
            if "uuid" in kw:
                self.uuid = UUID(hex=kw["uuid"])
            elif "serial" in kw:
                self.uuid = UUID(hex=kw["serial"])
            elif "usb_addr" in kw:
                self.usb_addr = int(kw["usb_addr"])
            else:
                raise SystemError("Poor connection configuration")
            self.POOL_TIME = 1.5

        def on_connected(self):
            pass

        def on_loop(self):
            pass

        def get_robot_from_device(self, device):
            return device.connect_robot(
                self.client_key, conn_callback=self._conn_callback)

        def get_robot_from_h2h(self, usbprotocol):
            return FluxRobot.from_usb(self.client_key, usbprotocol)

        def try_connect(self):
            self.send_text(STAGE_DISCOVER)
            if self.uuid:
                uuid = self.uuid

                if uuid in self.server.discover_devices:
                    device = self.server.discover_devices[uuid]
                    self.remote_version = device.version
                    self.send_text(STAGE_CONNECTIONG)

                    try:
                        self.robot = self.get_robot_from_device(device)

                    except (OSError, ConnectionError, socket.timeout) as e:  # noqa
                        logger.error("Socket erorr: %s", e)
                        self.send_fatal("DISCONNECTED")

                    except (RobotError, RobotSessionError) as err:
                        if err.error_symbol[0] == "REMOTE_IDENTIFY_ERROR":
                            self.server.discover_devices.pop(uuid)
                            self.server.discover.devices.pop(uuid)
                        self.send_fatal(*err.error_symbol)
                        return

                else:
                    self.send_fatal("NOT_FOUND")

            elif self.usb_addr:
                usbprotocol = g.USBDEVS.get(self.usb_addr)
                self.send_text(STAGE_CONNECTIONG)

                if usbprotocol:
                    self.remote_version = StrictVersion(
                        usbprotocol.endpoint_profile["version"])

                    self.robot = self.get_robot_from_h2h(usbprotocol)
                else:
                    self.send_fatal("UNKNOWN_DEVICE")
            else:
                self.send_fatal("?")

            self.send_text(STAGE_CONNECTED)
            self.POOL_TIME = 30.0
            self.on_connected()

        def on_text_message(self, message):
            if self.client_key:
                self.on_command(message)
            else:
                try:
                    self.client_key = KeyObject.load_keyobj(message)
                    self.try_connect()
                except ValueError:
                    self.send_fatal("BAD_PARAMS")
                except Exception:
                    logger.error("RSA Key load error: %s", message)
                    self.send_fatal("BAD_PARAMS")
                    raise

        def on_binary_message(self, buf):
            try:
                if self.binary_handler:
                    self.binary_handler(buf)
                else:
                    self.send_fatal("PROTOCOL_ERROR",
                                    "Can not accept binary data")
            except RobotSessionError as e:
                logger.debug("RobotSessionError%s [error_symbol=%s]",
                             repr(e.args), e.error_symbol)
                self.send_fatal(*e.error_symbol)

        def cb_upload_callback(self, robot, sent, size):
            self.send_json(status="uploading", sent=sent)

        def simple_binary_transfer(self, method, mimetype, size,
                                   upload_to=None, cb=None):
            ref = method(mimetype, size, upload_to)

            def binary_handler(buf):
                try:
                    feeder = ref.__next__()
                    sent = feeder(buf)
                    self.send_json(status="uploading", sent=sent)
                    if sent == size:
                        ref.__next__()
                except StopIteration:
                    self.binary_handler = None
                    cb()

            ref.__next__()
            self.binary_handler = binary_handler
            self.send_continue()

        def simple_binary_receiver(self, size, continue_cb):
            swap = BytesIO()
            upload_meta = {'sent': 0}

            def binary_handler(buf):
                swap.write(buf)
                sent = upload_meta['sent'] = upload_meta['sent'] + len(buf)

                if sent < size:
                    pass
                elif sent == size:
                    self.binary_handler = None
                    continue_cb(swap)
                else:
                    self.send_fatal("NOT_MATCH", "binary data length error")

            self.binary_handler = binary_handler
            self.send_continue()

        def _fix_auth_error(self, task):
            self.send_text(STAGE_DISCOVER)
            if task.timedelta < -15:
                logger.warn("Auth error, try fix time delta")
                old_td = task.timedelta
                task.reload_remote_profile(lookup_timeout=30.)
                if task.timedelta - old_td > 0.5:
                    # Fix timedelta issue let's retry
                    p = self.server.discover_devices.get(self.uuid)
                    if p:
                        p["timedelta"] = task.timedelta
                        self.server.discover_devices[self.uuid] = p
                        return True
            return False

        def on_closed(self):
            if self.robot:
                self.robot.close()
                self.robot = None
            self.cmd_mapping = None

        def _disc_callback(self, *args):
            self.send_text(STAGE_DISCOVER)
            return True

        def _conn_callback(self, *args):
            self.send_text(STAGE_CONNECTIONG)
            return True
    return ControlBaseAPI
