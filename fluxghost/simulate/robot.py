from fluxclient.robot.errors import RobotError

from .failedimg import IMAGE_BUF, IMAGE_MIMETYPE
from .filesystem import get_simulate_file_info, get_simulate_path


class SimulateRobot:
    selected_node = None

    def __init__(self, device):
        self.device = device

    def list_files(self, path):
        is_dir, node = get_simulate_path(path)
        if is_dir:
            folders = tuple((True, name) for name in node['folders'])
            files = tuple((False, name) for name in node['files'])
            return folders + files
        else:
            raise RobotError('Not a folder', error_symbol=['NOT_EXIST', 'BAD_NODE22'])

    def file_info(self, path):
        return get_simulate_file_info(path), ((IMAGE_MIMETYPE, IMAGE_BUF),)

    def close(self):
        pass

    def select_file(self, path):
        self.selected_node = get_simulate_file_info(path)

    def report_play(self):
        return self.device.simulate_report_play()

    def start_play(self):
        if self.selected_node:
            self.device.simulate_start_player(self.selected_node)
        else:
            raise RobotError(error_symbol=['NO_TASK'])

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

    def scan_backward(self):
        pass

    def scan_next(self):
        pass
