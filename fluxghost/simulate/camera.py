import os
import socket
from threading import Thread
from time import sleep

SIMULATE_CAMERA_FILE = os.path.join(os.path.dirname(__file__), '..', 'assets', 'flux-icon.png')


class SimulateCamera:
    def __init__(self):
        self.__running = True

        try:
            with open(SIMULATE_CAMERA_FILE, 'rb') as f:
                self._buf = f.read()
        except Exception:
            from .failedimg import IMAGE_BUF

            self._buf = IMAGE_BUF

        # A socketpair (not os.pipe) so the read end is selectable on Windows;
        # ApiBase._serve_forever selects on it and select() rejects non-socket
        # fds on Windows (WinError 10038).
        self._sock_r, self._sock_w = socket.socketpair()
        self._thread = Thread(target=self.__trigger)
        self._thread.daemon = True
        self._thread.start()

    def __trigger(self):
        while self.__running:
            self._sock_w.send(b'\x00')
            sleep(0.25)

    # TODO: remove
    @property
    def sock(self):
        return self

    def fileno(self):
        return self._fd_r

    def feed(self, callback):
        os.read(self._fd_r, 1)
        callback(self, self._buf)

    def close(self):
        if self.__running:
            self.__running = False
            os.close(self._fd_w)
            os.close(self._fd_r)
