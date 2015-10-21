
import logging
import json

from fluxclient.upnp.task import UpnpTask
from .base import WebSocketBase

logger = logging.getLogger("WS.DISCOVER")


class WebsocketTouch(WebSocketBase):
    def __init__(self, *args):
        WebSocketBase.__init__(self, *args)

    def on_text_message(self, message):
        try:
            payload = json.loads(message)
            serial = payload["serial"]
            password = payload.get("password")
            self.touch_device(serial, password)
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

    def touch_device(self, serial, password=None):
        try:
            if serial == "1111111111111111111111111":
                self.send_text(json.dumps({
                "serial": serial,
                "name": "Simulate Device",
                "has_response": True,
                "reachable": True,
                "auth": True
            }))

            task = UpnpTask(serial, lookup_timeout=30.0)
            resp = self._run_auth(task, password)

            self.send_text(json.dumps({
                "serial": serial,
                "name": task.name,
                "has_response": resp is not None,
                "reachable": task.remote_addr != "255.255.255.255",
                "auth": resp and resp.get("status") == "ok"
            }))

        except RuntimeError as err:
            logger.debug("Error: %s" % err)
            self.send_text(json.dumps({
                "serial": serial,
                "has_response": False,
                "reachable": False,
                "auth": False
            }))
