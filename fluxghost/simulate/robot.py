
from fluxclient.robot.errors import RobotError


class SimulateRobot(object):
    def __init__(self, device):
        self.device = device

    def list_files(self, entry, path=""):
        def gen_result():
            if path == "":
                return ((True, "folder1"), (True, "folder2"),
                        (False, "file1.fc"), (False, "file2.fc"))
            elif path in ("folder1", "folder1"):
                return [(False, "sub-file1.fc"), (False, "file2.fc")]
            else:
                raise RobotError("NOT_EXIST BAD_NODE")

        if entry in ("SD", "USB"):
            return gen_result()

        else:
            raise RobotError("NOT_EXIST BAD_ENTRY")

    def fileinfo(self, entry, path):
        return {}, None

    def close(self):
        pass

    def start_play(self):
        pass

    def pause_play(self):
        pass

    def resume_play(self):
        pass

    def abort_play(self):
        pass

    def quit_play(self):
        pass

    def kick(self):
        pass

    def maintain_home(self):
        pass

    def scan_backward(self):
        pass

    def scan_next(self):
        pass
