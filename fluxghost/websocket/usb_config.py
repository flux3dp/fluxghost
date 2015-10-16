
from glob import glob
import logging
import json
import sys

from serial.tools import list_ports as _list_ports
from fluxclient.usb.task import UsbTask, UsbTaskError

from .base import WebSocketBase

logger = logging.getLogger("WS.USBCONFIG")

# TODO
"""
This is a simple ECHO websocket for testing only

Javascript Example:

ws = new WebSocket("ws://localhost:8000/ws/usb-config");
ws.onmessage = function(v) { console.log(v.data);}
ws.onclose = function(v) { console.log("CONNECTION CLOSED, code=" + v.code +
    "; reason=" + v.reason); }

ws.onopen = function() {
    ws.send("list")
    ws.send("connect /dev/ttyUSB0")
}
"""


class WebsocketUsbConfig(WebSocketBase):
    task = None

    def list_ports(self):
        payload = {"status": "ok"}
        if sys.platform.startswith('darwin'):
            payload["ports"] = [s for s in glob('/dev/tty.*') if "Bl" not in s]
        else:
            payload["ports"] = [s[0] for s in _list_ports.comports()
                                if s[2] != "n/a"]

        self.send_text(json.dumps(payload))

    def connect_usb(self, port):
        if self.task:
            self.task.close()
            self.task = None

        self.task = t = UsbTask(port=port)
        self.send_text(
            json.dumps({"status": "ok", "serial": t.serial,
                        "version": t.remote_version, "name": t.name,
                        "model": t.model_id, "password": t.has_password}))

    def auth(self, password=None):
        if password:
            self.task.auth(password)
        else:
            self.task.auth()
        self.send_text('{"status": "ok"}')

    def config_general(self, params):
        options = json.loads(params)
        self.task.config_general(options)
        self.send_text('{"status": "ok"}')

    def config_network(self, params):
        options = json.loads(params)
        self.task.config_network(options)
        self.send_text('{"status": "ok"}')

    def get_network(self):
        payload = {"status": "ok", "ssid": None, "ipaddr": None}

        try:
            payload["ssid"] = self.task.get_ssid()
        except UsbTaskError:
            pass

        self.send_text(json.dumps(payload))

    def set_password(self, password):
        ret = self.task.set_password(password)
        if ret == "OK":
            self.send_text('{"status": "ok"}')
        else:
            self.send_error(ret)

    def on_text_message(self, message):
        try:
            if message == "list":
                self.list_ports()
            elif message.startswith("connect "):
                self.connect_usb(message.split(" ", 1)[-1])
            elif message == "auth":
                self.auth()
            elif message.startswith("auth "):
                self.auth(message[5:])
            elif message.startswith("set general "):
                self.config_general(message.split(" ", 2)[-1])
            elif message.startswith("set network "):
                self.config_network(message.split(" ", 2)[-1])
            elif message.startswith("get network"):
                self.get_network()
            elif message.startswith("set password "):
                self.set_password(message[13])
            else:
                self.send_text(
                    '{"status": "error", "error": "UNKNOW_COMMAND"}')

        except RuntimeError as e:
            self.send_text(json.dumps({"status": "error", "error":
                                       e.args[0]}))
        except Exception:
            logger.exception("Unhandle Error")
            self.send_text(json.dumps({"status": "error", "error":
                                       "UNKNOW_ERROR"}))

    def on_binary_message(self, buf):
        pass

    def on_close(self, message):
        if self.task:
            self.task.close()
            self.task = None
