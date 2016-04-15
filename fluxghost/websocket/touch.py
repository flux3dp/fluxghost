
from uuid import UUID
import logging
import json

from fluxclient.encryptor import KeyObject
from fluxclient.upnp import UpnpTask, AuthError, TimeoutError, UpnpError
from .base import WebSocketBase

logger = logging.getLogger("WS.DISCOVER")


class WebsocketTouch(WebSocketBase):
    def __init__(self, *args):
        WebSocketBase.__init__(self, *args)

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

            # TODO
            metadata = self.server.discover_devices.get(uuid)
            backend_options = {}

            if password:
                backend_options["password"] = password

            if metadata:
                UpnpTask(uuid, client_key=client_key, remote_profile=metadata,
                         backend_options=backend_options, lookup_timeout=30.0)
            else:
                UpnpTask(uuid, client_key=client_key,
                         backend_options=backend_options, lookup_timeout=30.0)

            self.send_text(json.dumps({
                "uuid": uuid.hex, "has_response": True, "reachable": True,
                "auth": True
            }))
        except AuthError:
            self.send_text(json.dumps({
                "uuid": uuid.hex, "has_response": True, "reachable": True,
                "auth": False
            }))
        except TimeoutError:
            self.send_text(json.dumps({
                "uuid": uuid.hex, "has_response": False, "reachable": False,
                "auth": False
            }))
        except (RuntimeError, UpnpError) as err:
            logger.debug("Error: %s" % err)
            self.send_text(json.dumps({
                "uuid": uuid.hex,
                "has_response": False,
                "reachable": False,
                "auth": False
            }))
