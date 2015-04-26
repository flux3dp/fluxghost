
from time import time
import logging
import json
import re

from .base import WebSocketBase

logger = logging.getLogger("WS.CONTROL")


"""
Control printer

Javascript Example:

ws = new WebSocket("ws://localhost:8080/ws/control/FFFFFFFFFFFFFFFFFFFFFFFFF");
ws.onmessage = function(v) { console.log(v.data);}
ws.onclose = function(v) { console.log("CONNECTION CLOSED, code=" + v.code +
    "; reason=" + v.reason); }

// After recive connected...
ws.send("ls")
"""

# >>>>>>>> FAKE_CODE
FAKE_FILES = ["file1.gcode", "file2.gcode"]
# <<<<<<<< FAKE_CODE


class WebsocketControl(WebSocketBase):
    @classmethod
    def match_route(klass, path):
        return True if re.match("control/[0-9A-Z]{25}", path) else False

    def __init__(self, *args, **kw):
        WebSocketBase.__init__(self, *args, **kw)

        self.POOL_TIME = 1.0

        # >>>>>>>> FAKE_CODE
        self._connected = False
        self._ts = time()

        self._file_selected = False
        self._upload_file_size = -1

        self._st = "STOP"
        self._progress = 0.0
        # <<<<<<<< FAKE_CODE

    def onMessage(self, message, is_binary):
        if is_binary:
            self.on_recv_binary(message)
        else:
            self.on_recv_text(message)

    def on_recv_binary(self, buf):
        if not self.connected:
            return

        # >>>>>>>> FAKE_CODE
        if self._upload_file_size > 0:
            self._upload_file_size -= len(buf)

            if self._upload_file_size == 0:
                self._upload_file_size = -1
                self._file_selected = True
                self.send_text("ok")
            elif self._upload_file_size < 0:
                self.send_text("error FILESIZE_ERROR")
        # <<<<<<<< FAKE_CODE

    def on_recv_text(self, message):
        if not self.connected:
            return

        # >>>>>>>> FAKE_CODE
        if message == "ls":
            self.send_text(json.dumps(FAKE_FILES))
        elif message.startswith("select "):
            filename = message.split(" ", 1)[-1]
            if filename in FAKE_FILES:
                self._file_selected = True
                self.send_text("ok")
            else:
                self.send_text("error FILE_NOT_FOUND")
        elif message.startswith("upload "):
            filesize = message.split(" ", 1)[-1]
            if filesize.isdigit():
                self._upload_file_size = int(filesize, 10)
                self.send_text("continue")
            else:
                self.send_text("error BAD_ARGS")
        elif message == "start":
            if self._file_selected:
                if self._st == "STOP":
                    self._st = "RUN"
                    self._progress = 0.0
                else:
                    self.send_text("error ALREADY_RUNNING")
            else:
                self.send_text("error NO_JOB")
        elif message == "pause":
            if self._st == "RUN":
                self._st = "PAUSE"
            else:
                self.send_text("error NOT_RUNNING")
        elif message == "resume":
            if self._st == "PAUSE":
                self._st = "RUN"
            else:
                self.send_text("error NOT_PAUSE")
        elif message == "stop":
            if self._st == "RUN" or self._st == "PAUSE":
                self._st = "STOP"
                self.send_text(json.dumps({
                    "status": "aborted" 
                }))
        # <<<<<<<< FAKE_CODE

    @property
    def connected(self):
        # >>>>>>>> FAKE_CODE
        return self._connected
        # <<<<<<<< FAKE_CODE

    def on_loop(self):
        # >>>>>>>> FAKE_CODE
        if time() - self._ts < 3.5:
            self.send_text("connecting")
        elif not self._connected:
            self._connected = True
            self.send_text("connected")

        if self._st == "RUN":
            self._progress += 0.15

            if self._progress < 1.0:
                self.send_text(json.dumps({
                    "status": "running",
                    "coordinate": [0.1, 0.2, 0.3],
                    "extruder1_temp": 123.0,
                    "fan1_speed": 123
                }))
            else:
                self.send_text(json.dumps({
                    "status": "completed" 
                }))
                self._st = "STOP"
        elif self._st == "PAUSE":
            self.send_text(json.dumps({
                "status": "pause",
                "coordinate": [0.1, 0.2, 0.3],
                "extruder1_temp": 123.0,
                "fan1_speed": 123
            }))
        # <<<<<<<< FAKE_CODE


