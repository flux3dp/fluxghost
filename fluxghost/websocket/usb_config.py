
from glob import glob
import logging
import json
import sys

from serial.tools import list_ports as _list_ports
from fluxclient.encryptor import KeyObject
from fluxclient.usb.task import UsbTask

from .base import WebSocketBase

logger = logging.getLogger("WS.USBCONFIG")

"""
This is a simple Usb websocket

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
    client_key = None

    def __init__(self, *args, **kw):
        super(WebsocketUsbConfig, self).__init__(*args, **kw)
        self.task = NoneTask()

    def list_ports(self):
        payload = {"status": "ok"}
        if sys.platform.startswith('darwin'):
            payload["ports"] = [s for s in glob('/dev/tty.*') if "Bl" not in s]
        else:
            payload["ports"] = [s[0] for s in _list_ports.comports()
                                if s[2] != "n/a"]

        self.send_json(payload)

    def connect_usb(self, port):
        if self.task:
            self.task.close()
            self.task = None

        try:
            if not self.client_key:
                self.send_json(status="error", error="KEY_ERROR")
                return

            if port == "SIMULATE":
                self.task = t = SimulateTask()
            else:
                self.task = t = UsbTask(port=port, client_key=self.client_key)
            self.send_json(status="ok", cmd="connect", serial=t.serial,
                           version=t.remote_version, name=t.name,
                           model=t.model_id, password=t.has_password)
        except Exception as e:
            self.send_json(status="error", error="DEVICE_ERROR", info=repr(e))
            logger.exception("Error while connect to usb")

    def auth(self, password=None):
        if password:
            self.task.auth(password)
        else:
            self.task.auth()
        self.send_text('{"status": "ok", "cmd": "auth"}')

    def config_general(self, params):
        options = json.loads(params)
        self.task.config_general(options)
        self.send_text('{"status": "ok"}')

    def scan_wifi(self):
        ret = self.task.list_ssid()
        self.send_json(status="ok", cmd="scan", wifi=ret)

    def config_network(self, params):
        options = json.loads(params)
        self.task.config_network(options)
        self.send_text('{"status": "ok"}')

    def get_network(self):
        payload = {"status": "ok", "cmd": "network"}
        payload["ssid"] = self.task.get_ssid()
        payload["ipaddr"] = self.task.get_ipaddr()
        self.send_json(payload)

    def set_password(self, password):
        ret = self.task.set_password(password)
        if ret == "OK":
            self.send_text('{"status": "ok", "cmd": "password"}')
        else:
            self.send_error(ret)

    def on_text_message(self, message):
        try:
            if message == "list":
                self.list_ports()
            elif message.startswith("key "):
                pem = message.split(" ", 1)
                self.client_key = KeyObject.load_keyobj(pem)
                self.send_json(status="ok")
            elif message.startswith("connect "):
                self.connect_usb(message.split(" ", 1)[-1])
            elif message == "auth":
                self.auth()
            elif message.startswith("auth "):
                self.auth(message[5:])
            elif message.startswith("set general "):
                self.config_general(message.split(" ", 2)[-1])
            elif message == "scan_wifi":
                self.scan_wifi()
            elif message.startswith("set network "):
                self.config_network(message.split(" ", 2)[-1])
            elif message.startswith("get network"):
                self.get_network()
            elif message.startswith("set password "):
                self.set_password(message[13:])
            else:
                self.send_error("UNKNOWN_COMMAND")

        except RuntimeError as e:
            self.send_json(status="error", error=e.args[0])
        except Exception:
            logger.exception("Unhandle Error")
            self.send_error("UNKNOWN_ERROR")

    def on_binary_message(self, buf):
        pass

    def on_close(self, message):
        if self.task:
            self.task.close()
            self.task = None


class NoneTask(object):
    def __getattr__(self, name):
        raise RuntimeError("NOT_CONNECTED")

    def close(self):
        pass


class SimulateTask(object):
    remote_version = "1.0"
    name = "simulate_device"
    model_id = "SIMULATE"
    serial = "SIMULATE"
    has_password = True

    def __init__(self, port=None):
        pass

    def auth(self, password=None):
        if password != "WAGAMAMA":
            raise RuntimeError("BAD_PASSWORD")

    def close(self):
        pass
