
import logging

from .base import WebSocketBase

logger = logging.getLogger("WS.FILE")

WRITE_OP = "w"
READ_OP = "r"


"""
Read or write file

// Read file
    ws = new WebSocket("ws://localhost:8000/ws/file");
    // Recive filestream in binary
    ws.onmessage = function(v) { console.log(v.data);}
    ws.onopen = function() {
        ws.send("r file/path/on/your/disk")
    }

// Write file
    ws = new WebSocket("ws://localhost:8080/ws/file");
    ws.onopen = function() {
        ws.send("w file/path/on/your/disk")
        buf = new ArrayBuffer(10000)
        ws.send(buf)
        ws.close()
    }
"""


class WebsocketFile(WebSocketBase):
    fileobj = None
    operation = None

    def on_close(self, *args, **kw):
        super(WebsocketFile, self).on_close(*args, **kw)
        self.close_file()

    def on_text_message(self, message):
        op, file = message.split(" ", 1)

        try:
            if self.operation:
                raise RuntimeError("FILE_ALREADY_OPENED")

            if op == WRITE_OP:
                self.operation = WRITE_OP
                self.fileobj = open(file, "wb")
                self.send("opened")
            elif op == READ_OP:
                self.operation = READ_OP
                self.fileobj = open(file, "rb")
                self.send("opened")
                self.send_file()
            else:
                raise RuntimeError("BAD_FILE_OPERATION")

        except RuntimeError as e:
            self.send("error %s" % e.args[0])
            self.close()
        except FileNotFoundError:
            self.send("error FILE_NOT_EXIST")
            self.close()
        except PermissionError:
            self.send("error ACCESS_DENY")
            self.close()
        except Exception as e:
            self.send("error UNKNOW_ERROR %s" % e)
            self.close()

    def on_binary_message(self, buf):
        if self.operation == WRITE_OP:
            self.fileobj.write(buf)

    def send_file(self):
        buf = bytearray(1024)
        mv = memoryview(buf)
        while True:
            l = self.fileobj.readinto(buf)
            if l:
                self.send_binary(mv[:l])
            else:
                self.close()

    def close_file(self):
        if self.fileobj:
            try:
                self.fileobj.close()
            except Exception:
                pass
            self.fileobj = None
