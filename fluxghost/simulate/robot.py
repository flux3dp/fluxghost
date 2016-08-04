
from fluxclient.robot.errors import RobotError
from .filesystem import get_simulate_path, get_simulate_file_info
from .failedimg import IMAGE_MIMETYPE, IMAGE_BUF


class SimulateRobot(object):
    def __init__(self, device):
        self.device = device

    def list_files(self, path):
        is_dir, node = get_simulate_path(path)
        if is_dir:
            folders = tuple(((True, name) for name in node["folders"].keys()))
            files = tuple(((False, name) for name in node["files"].keys()))
            return folders + files
        else:
            raise RobotError("Not a folder",
                             error_symbol=["NOT_EXIST", "BAD_NODE22"])

    def file_info(self, path):
        return get_simulate_file_info(path), ((IMAGE_MIMETYPE, IMAGE_BUF), )

    def close(self):
        pass

    def select_file(self, file):
        pass

    # def report_play(self):
    #     return self.device.simulate_report_play()

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
