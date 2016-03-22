
from uuid import UUID
import logging
import json

from fluxclient.encryptor import KeyObject
from fluxclient.upnp.task import UpnpTask
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
            if uuid.hex == "0" * 32:
                self.send_text(json.dumps({
                    "serial": "SIMULATE00",
                    "name": "Simulate Device",
                    "has_response": True,
                    "reachable": True,
                    "auth": True
                }))
                return

            # TODO
            profile = self.server.discover_devices.get(uuid)
            if profile:
                task = UpnpTask(uuid, client_key=client_key,
                                remote_profile=profile, lookup_timeout=30.0)
            else:
                task = UpnpTask(uuid, client_key=client_key,
                                lookup_timeout=30.0)

            resp = self._run_auth(task, password)

            self.send_text(json.dumps({
                "uuid": uuid.hex,
                "serial": task.serial,
                "name": task.name,
                "has_response": resp is not None,
                "reachable": True,
                "auth": resp and resp.get("status") == "ok"
            }))

        except RuntimeError as err:
            logger.debug("Error: %s" % err)
            self.send_text(json.dumps({
                "uuid": uuid.hex,
                "has_response": False,
                "reachable": False,
                "auth": False
            }))
