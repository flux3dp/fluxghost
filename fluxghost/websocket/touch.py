
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

    def touch_device(self, serial, password=None):
        try:
            task = UpnpTask(serial, lookup_timeout=30.0)
            if password:
                resp = task.auth_with_password(password)
            else:
                resp = task.auth_without_password()

            self.send_text(json.dumps({
                "serial": serial,
                "has_response": resp != None,
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