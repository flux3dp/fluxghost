
from getpass import getuser
from uuid import UUID
import logging
import json

from fluxclient.encryptor import KeyObject
from fluxclient.device.manager import DeviceManager, ManagerError

logger = logging.getLogger("API.TOUCH")


def touch_api_mixin(cls):
    class TouchApi(cls):
        def __init__(self, *args):
            super().__init__(*args)

        def on_text_message(self, message):
            try:
                payload = json.loads(message)
                uuid = UUID(hex=payload["uuid"])
                client_key = KeyObject.load_keyobj(payload["key"])
                password = payload.get("password")

                self.touch_device(client_key, uuid, password)
            except Exception:
                logger.exception("Touch error")
                self.close()

        def _run_auth(self, task, password=None):
            ttl = 3
            while True:
                try:
                    if password:
                        return task.auth_with_password(password)
                    else:
                        return task.auth_without_password()
                except RuntimeError as e:
                    if e.args[0] == "TIMEOUT" and ttl > 0:
                        logger.warn("Remote no response, retry")
                        ttl -= 1
                    else:
                        raise

        def touch_device(self, client_key, uuid, password=None):
            try:
                if uuid.int == 0:
                    self.send_text(json.dumps({
                        "serial": "SIMULATE00",
                        "name": "Simulate Device",
                        "has_response": True,
                        "reachable": True,
                        "auth": True
                    }))
                    return

                device = self.server.discover_devices.get(uuid)

                try:
                    if device:
                        task = device.manage_device(client_key)
                    else:
                        task = DeviceManager.from_uuid(uuid,
                                                       client_key=client_key,
                                                       lookup_timeout=30.0)
                except IOError as e:
                    logger.warning("%s", e)
                    self.send_text(json.dumps({
                        "uuid": uuid.hex, "has_response": False,
                        "reachable": False, "auth": False
                    }))
                    return

                if not task.authorized:
                    if password:
                        task.authorize_with_password(password)
                    else:
                        self.send_text(json.dumps({
                            "uuid": uuid.hex, "has_response": True,
                            "reachable": True, "auth": False}))
                        return
                try:
                    task.add_trust(getuser(),
                                   client_key.public_key_pem.decode())
                except ManagerError:
                    pass

                self.send_text(json.dumps({
                    "uuid": uuid.hex, "has_response": True, "reachable": True,
                    "auth": True
                }))

            except ManagerError as e:
                if e.err_symbol == ("AUTH_ERROR", ):
                    self.send_text(json.dumps({
                        "uuid": uuid.hex, "has_response": True,
                        "reachable": True, "auth": False
                    }))
                elif e.err_symbol == ("TIMEOUT", ):
                    self.send_text(json.dumps({
                        "uuid": uuid.hex, "has_response": True,
                        "reachable": True, "auth": False
                    }))
                else:
                    logger.error("Touch error: %s", e.err_symbol)
                    self.send_text(json.dumps({
                        "uuid": uuid.hex, "has_response": True,
                        "reachable": True, "auth": False
                    }))

            except RuntimeError as err:
                logger.debug("Error: %s" % err)
                self.send_text(json.dumps({
                    "uuid": uuid.hex,
                    "has_response": False,
                    "reachable": False,
                    "auth": False
                }))
    return TouchApi
