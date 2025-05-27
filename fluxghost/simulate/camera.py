import os
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

        self._fd_r, self._fd_w = os.pipe()
        self._thread = Thread(target=self.__trigger)
        self._thread.daemon = True
        self._thread.start()

    def __trigger(self):
        while self.__running:
            os.write(self._fd_w, b'\x00')
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
