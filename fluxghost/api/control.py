
from errno import EPIPE
from io import BytesIO
from time import time, sleep
import json
import logging
import pipes
import socket
import shlex
import string

from fluxclient.device.host2host_usb import FluxUSBError
from fluxclient.robot.errors import RobotError, RobotSessionError
from fluxclient.utils.version import StrictVersion
from fluxclient.fcode.g_to_f import GcodeToFcode
from fluxclient.robot.robot import RawTasks

from .control_base import control_base_mixin

logger = logging.getLogger("API.CONTROL")


STAGE_DISCOVER = '{"status": "connecting", "stage": "discover"}'
STAGE_ROBOT_CONNECTING = '{"status": "connecting", "stage": "connecting"}'
STAGE_CONNECTED = '{"status": "connected"}'
STAGE_TIMEOUT = '{"status": "error", "error": "TIMEOUT"}'


def control_api_mixin(cls):
    class ControlApi(control_base_mixin(cls)):
        _task = None
        _task_sockets = None

        @property
        def task_sockets(self):
            if not self._task_sockets:
                self._task_sockets = {}
            return self._task_sockets

        def on_connected(self):
            self.set_hooks()

        def set_hooks(self):
            if self.remote_version < StrictVersion("1.0b13"):
                logger.warn("Remote version is too old, allow update fw only")
                self.cmd_mapping = {
                    "update_fw": self.update_fw,
                }
                return

            self.cmd_mapping = {
                # deprecated
                "ls": self.list_file,
                # deprecated
                "select": self.select_file,
                # deprecated
                "mkdir": self.mkdir,
                # deprecated
                "rmdir": self.rmdir,
                # deprecated
                "rmfile": self.rmfile,
                # deprecated
                "cpfile": self.cpfile,
                # deprecated
                "fileinfo": self.fileinfo,
                # deprecated
                "upload": self.upload_file,
                "update_fw": self.update_fw,
                "update_laser_records": self.update_laser_records,
                "update_fisheye_params": self.update_fisheye_params,
                'update_fisheye_3d_rotation': self.update_fisheye_3d_rotation,
                "update_mbfw": self.update_mbfw,

                "deviceinfo": self.deviceinfo,
                "cloud_validate_code": self.cloud_validate_code,
                "wait_status": self.wait_status,
                "kick": self.kick,

                "file": {
                    "lsusb": self.list_usb,
                    "ls": self.list_file,
                    "mkdir": self.mkdir,
                    "rmdir": self.rmdir,
                    "rm": self.rmfile,
                    "rmfile": self.rmfile,
                    "cp": self.cpfile,
                    "cpfile": self.cpfile,
                    "info": self.fileinfo,
                    "fileinfo": self.fileinfo,
                    "md5": self.filemd5,
                    "upload": self.upload_file,
                    "download": self.download,
                    "download2": self.download2,
                },

                "config": {
                    "set": self.config_set,
                    "set_json": self.config_set_json,
                    "get": self.config_get,
                    "del": self.config_del
                },

                "pipe": {
                    "set": self.pipe_set,
                    "get": self.pipe_get,
                    "del": self.pipe_del
                },

                "play": {
                    "select": self.select_file,
                    "start": self.start_play,
                    "preview": self.preview_play,
                    "info": self.play_info,
                    "report": self.report_play,
                    "pause": self.pause_play,
                    "resume": self.resume_play,
                    "abort": self.abort_play,
                    'restart': self.restart_play,
                    "set_laser_power": self.set_laser_power,
                    "set_laser_power_temp": self.set_laser_power_temp,
                    "get_laser_power": self.get_laser_power,
                    "set_laser_speed": self.set_laser_speed,
                    "set_laser_speed_temp": self.set_laser_speed_temp,
                    "get_laser_speed": self.get_laser_speed,
                    "set_fan": self.set_fan,
                    "set_fan_temp": self.set_fan_temp,
                    "get_fan": self.get_fan,
                    'set_origin_x': self.set_origin_x,
                    'set_origin_y': self.set_origin_y,
                    "get_door_open": self.get_door_open,
                    "get": self.player_get,
                    "toolhead": {
                        "operation": self.set_toolhead_operating,
                        "standby": self.set_toolhead_standby,
                        "heater": self.set_toolhead_heater,
                    },
                    "press_button": self.press_button_in_play,
                    "quit": self.quit_play
                },

                'task': self.handle_task_command,

                "fetch_log": self.fetch_log,
                "fetch_laser_records": self.fetch_laser_records,
                "fetch_camera_calib_pictures": self.fetch_camera_calib_pictures,
                "fetch_fisheye_params": self.fetch_fisheye_params,
                'fetch_fisheye_3d_rotation': self.fetch_fisheye_3d_rotation,
                "fetch_auto_leveling_data": self.fetch_auto_leveling_data,
                "jsonrpc_req": self.jsonrpc_req,
            }

        @property
        def task(self):
            if not self._task:
                raise RuntimeError("OPERATION_ERROR")
            return self._task

        @task.setter
        def task(self, val):
            self._task = val

        def get_task_socket(self, task_type):
            return self.task_sockets.get(task_type, None)

        def add_task_socket(self, task_type, socket):
            self.task_sockets[task_type] = socket
            self.rlist.append(socket)

        def remove_task_socket(self, task_type):
            socket = self.task_sockets.get(task_type, None)
            if socket:
                self.rlist.remove(socket)
                del self.task_sockets[task_type]

        def invoke_command(self, ref, args, wrapper=None):
            if not args:
                return False

            cmd = args[0]
            if cmd in ref:
                obj = ref[cmd]
                if isinstance(obj, dict):
                    return self.invoke_command(obj, args[1:], wrapper)
                else:
                    if wrapper:
                        wrapper(obj, *args[1:])
                    else:
                        obj(*args[1:])
                    return True
            return False

        def on_command(self, message):
            if message == "ping":
                self.send_text('{"status": "pong"}')
                return
            if isinstance(self._task, RawTasks):
                logger.info('Raw: => %s' % message)
                self.on_raw_message(message)
                return
            elif self._task:
                task_name = getattr(self._task, 'task_name', '')
                logger.info('Task %s: => %s' % (task_name, message))
                self.on_sub_task_message(message)
                return

            args = shlex.split(message)

            try:
                if self.invoke_command(self.cmd_mapping, args):
                    pass
                else:
                    logger.warn("Unknown Command: %s" % message)
                    self.send_error("L_UNKNOWN_COMMAND")

            except RobotError as e:
                logger.debug("RobotError%s [error_symbol=%s]", repr(e.args),
                             e.error_symbol)
                self.send_error(e.error_symbol)

            except RobotSessionError as e:
                logger.debug("RobotSessionError%s [error_symbol=%s]",
                             repr(e.args), e.error_symbol)
                self.send_fatal(e.error_symbol)

            except FluxUSBError as e:
                logger.debug("USB Error%s [error_symbol=%s]",
                             repr(e.args), e.symbol)
                self.send_fatal(e.symbol)
            except RuntimeError as e:
                logger.debug("RuntimeError Error%s", repr(e.args))
                self.send_error(e.args)

            except (TimeoutError, ConnectionResetError,  # noqa
                    socket.timeout, ) as e:
                from fluxclient.robot.robot import FluxRobot
                import sys
                _, _, t = sys.exc_info()
                while t.tb_next:
                    t = t.tb_next
                    if "self" in t.tb_frame.f_locals:
                        if isinstance(t.tb_frame.f_locals["self"], FluxRobot):
                            self.send_fatal("TIMEOUT", repr(e.args))
                            return
                self.send_traceback("L_UNKNOWN_ERROR", repr(e.__class__))

            except socket.error as e:
                if e.args[0] == EPIPE:
                    self.send_fatal("DISCONNECTED", repr(e.__class__))
                else:
                    logger.exception("Unknow socket error")
                    self.send_fatal("L_UNKNOWN_ERROR", repr(e.__class__))

            except Exception as e:
                logger.exception("Unknow error while process command")
                self.send_traceback("L_UNKNOWN_ERROR", repr(e.__class__))

        def kick(self):
            self.robot.kick()
            self.send_ok()

        def list_file(self, location="", *args):
            if len(args) > 0:
                location = location + " " + " ".join(args)
            if location and location != "/":
                path = location if location.startswith("/") else "/" + location
                dirs = []
                files = []
                for is_dir, name in self.robot.list_files(path):
                    if is_dir:
                        dirs.append(name)
                    else:
                        files.append(name)

                dirs.sort()
                files.sort()
                self.send_ok(path=location, directories=dirs,
                             files=files)
            else:
                self.send_ok(path=location,
                             directories=["SD", "USB"], files=[])

        def list_usb(self):
            ret = self.robot.list_usb().split('\n')
            ok = ret[0]
            ret = ret[1:-1]
            self.send_ok(cmd='lsusb' ,usbs=ret)

        def select_file(self, file, *args):
            if len(args) > 0:
                file = file + " " + " ".join(args)
            path = file if file.startswith("/") else "/" + file
            self.robot.select_file(path)
            self.send_ok(path=path)

        def fileinfo(self, file, *args):
            if len(args) > 0:
                file = file + " " + " ".join(args)
            path = file if file.startswith("/") else "/" + file
            info, binary = self.robot.file_info(path)
            if binary:
                # TODO
                self.send_json(status="binary", mimetype=binary[0][0],
                               size=len(binary[0][1]))
                self.send_binary(binary[0][1])

            self.send_ok(**info)

        def filemd5(self, file):
            path = file if file.startswith("/") else "/" + file
            hash = self.robot.file_md5(path)
            self.send_ok(file=path, md5=hash)

        def mkdir(self, file):
            path = file if file.startswith("/") else "/" + file
            if path.startswith("/SD/"):
                self.robot.mkdir(path)
                self.send_json(status="ok", path=path)
            else:
                self.send_error("NOT_SUPPORT")

        def rmdir(self, file):
            path = file if file.startswith("/") else "/" + file
            if path.startswith("/SD/"):
                self.robot.rmdir(path)
                self.send_ok(path=path)
            else:
                self.send_error("NOT_SUPPORT")

        def rmfile(self, file):
            path = file if file.startswith("/") else "/" + file
            self.robot.rmfile(path)
            self.send_json(status="ok", path=path)

        def download(self, file):
            def report(left, size):
                self.send_json(status="continue", left=left, size=size)

            path = file if file.startswith("/") else "/" + file
            buf = BytesIO()
            mimetype = self.robot.download_file(path, buf, report)
            if mimetype:
                self.send_json(status="binary", mimetype=mimetype,
                               size=buf.truncate())
                self.send_binary(buf.getvalue())

        def download2(self, file):
            flag = []

            def report(left, size):
                if not flag:
                    flag.append(1)
                    self.send_json(status="transfer", completed=0, size=size)
                self.send_json(status="transfer",
                               completed=(size - left), size=size)

            path = file if file.startswith("/") else "/" + file
            buf = BytesIO()
            mimetype = self.robot.download_file(path, buf, report)
            if mimetype:
                self.send_json(status="binary", mimetype=mimetype,
                               size=buf.truncate())
                self.send_binary(buf.getvalue())
                self.send_ok()

        def cpfile(self, source, target):
            spath = source if source.startswith("/") else "/" + source
            tpath = target if target.startswith("/") else "/" + target
            self.robot.cpfile(spath, tpath)
            self.send_ok(source=source, target=target)

        def upload_file(self, mimetype, ssize, upload_to="#"):
            if upload_to == "#":
                pass
            elif not upload_to.startswith("/"):
                upload_to = "/" + upload_to

            size = int(ssize)
            if mimetype == "text/gcode":
                if upload_to.endswith('.gcode'):
                    upload_to = upload_to[:-5] + 'fc'

                def upload_callback(swap):
                    gcode_content = swap.getvalue().decode("ascii", "ignore")
                    gcode_content = gcode_content.split('\n')

                    fcode_output = BytesIO()
                    g2f = GcodeToFcode()
                    g2f.process(gcode_content, fcode_output)

                    fcode_len = fcode_output.truncate()
                    fcode_output.seek(0)
                    self.send_json(status="uploading", sent=0,
                                   amount=fcode_len)
                    self.robot.upload_stream(fcode_output, 'application/fcode',
                                             fcode_len, upload_to,
                                             self.cb_upload_callback)
                    self.send_ok()

                self.simple_binary_receiver(size, upload_callback)
            else:
                self.simple_binary_transfer(self.robot.transfer_upload_stream, mimetype, size, upload_to=upload_to, cb=self.send_ok)
            return

        def update_fw(self, mimetype, ssize):
            size = int(ssize)

            def on_recived(stream):
                stream.seek(0)
                try:
                    self.robot.update_firmware(stream, int(size),
                                               self.cb_upload_callback)
                    self.send_ok()
                    self.close()
                except RobotError as e:
                    logger.debug("RobotError%s [error_symbol=%s]",
                                 repr(e.args), e.error_symbol)
                    self.send_error(e.error_symbol)
            self.simple_binary_receiver(size, on_recived)

        def update_laser_records(self, mimetype, ssize):
            size = int(ssize)
            def on_recived(stream):
                stream.seek(0)
                try:
                    self.robot.update_laser_records(stream, int(size),
                                                    self.cb_upload_callback)
                    self.send_ok()
                    self.close()
                except RobotError as e:
                    logger.debug("RobotError%s [error_symbol=%s]",
                                 repr(e.args), e.error_symbol)
                    self.send_error(e.error_symbol)
            self.simple_binary_receiver(size, on_recived)

        def update_fisheye_params(self, mimetype, ssize):
            size = int(ssize)
            def on_recived(stream):
                stream.seek(0)
                try:
                    self.robot.update_fisheye_params(stream, int(size),
                                                    self.cb_upload_callback)
                    self.send_ok()
                    self.close()
                except RobotError as e:
                    logger.debug("RobotError%s [error_symbol=%s]",
                                 repr(e.args), e.error_symbol)
                    self.send_error(e.error_symbol)
            self.simple_binary_receiver(size, on_recived)

        def update_fisheye_3d_rotation(self, mimetype, ssize):
            size = int(ssize)
            def on_recived(stream):
                stream.seek(0)
                try:
                    self.robot.update_fisheye_3d_rotation(stream, int(size),
                                                    self.cb_upload_callback)
                    self.send_ok()
                    self.close()
                except RobotError as e:
                    logger.debug("RobotError%s [error_symbol=%s]",
                                 repr(e.args), e.error_symbol)
                    self.send_error(e.error_symbol)
            self.simple_binary_receiver(size, on_recived)

        def update_mbfw(self, mimetype, ssize):
            size = int(ssize)

            def on_recived(stream):
                stream.seek(0)
                self.robot._backend.update_atmel(self.robot, stream, int(size),
                                                 self.cb_upload_callback)
                self.send_ok()
            self.simple_binary_receiver(size, on_recived)

        def start_play(self):
            self.robot.start_play()
            self.send_ok()

        def preview_play(self):
            self.robot.preview_play()
            self.send_ok()

        def pause_play(self):
            self.robot.pause_play()
            self.send_ok()

        def resume_play(self):
            self.robot.resume_play()
            self.send_ok()

        def abort_play(self):
            self.robot.abort_play()
            self.send_ok()

        def restart_play(self):
            self.robot.restart_play()
            self.send_ok()

        def set_laser_power(self, value):
            self.robot.set_laser_power(float(value))
            self.send_ok()

        def set_laser_power_temp(self, value):
            self.robot.set_laser_power_temp(float(value))
            self.send_ok()

        def set_laser_speed(self, value):
            self.robot.set_laser_speed(float(value))
            self.send_ok()

        def set_laser_speed_temp(self, value):
            self.robot.set_laser_speed_temp(float(value))
            self.send_ok()

        def set_fan(self, value):
            self.robot.set_fan(int(value))
            self.send_ok()

        def set_fan_temp(self, value):
            self.robot.set_fan_temp(int(value))
            self.send_ok()

        def set_origin_x(self, value):
            self.robot.set_origin_x(float(value))
            self.send_ok()

        def set_origin_y(self, value):
            self.robot.set_origin_y(float(value))
            self.send_ok()

        def get_laser_power(self):
            power = self.robot.get_laser_power()
            self.send_ok(value=power)

        def get_laser_speed(self):
            speed = self.robot.get_laser_speed()
            self.send_ok(value=speed)

        def get_fan(self):
            fan = self.robot.get_fan()
            self.send_ok(value=fan)

        def get_door_open(self):
            val = self.robot.get_door_open()
            self.send_ok(value=val)

        def player_get(self, key):
            val = self.robot.player_get(key)
            self.send_ok(value=val)

        def set_toolhead_operating(self):
            self.robot.set_toolhead_operating_in_play()
            self.send_ok()

        def set_toolhead_standby(self):
            self.robot.set_toolhead_standby_in_play()
            self.send_ok()

        def set_toolhead_heater(self, index, temp):
            self.robot.set_toolhead_heater_in_play(float(temp), int(index))
            self.send_ok()

        def press_button_in_play(self):
            self.robot.press_button_in_play()
            self.send_ok()

        def quit_play(self):
            self.robot.quit_play()
            self.send_ok()

        def handle_task_command(self, task_type):
            if task_type == 'quit':
                self.task_quit()
                return
            if task_type == 'raw':
                self.task_begin_raw()
                return
            method_map = {
                'cartridge_io': self.robot.cartridge_io,
                'red_laser_measure': self.robot.red_laser_measure,
                'z_speed_limit_test': self.robot.z_speed_limit_test,
            }
            method = method_map.get(task_type, None)
            if method is None:
                self.send_error("Unknown task: {}".format(task_type))
                return
            self.task = method()
            self.send_ok(task=task_type)

        def task_begin_raw(self):
            self.task = self.robot.raw()
            sock = PipeSocket(self.task.sock, self, 'raw')
            self.add_task_socket('raw', sock)
            self.send_ok(task="raw")

        def task_quit(self):
            self.task.quit()
            self.task = None
            self.send_ok(task="")

        def deviceinfo(self):
            self.send_ok(**self.robot.deviceinfo)

        def cloud_validate_code(self):
            self.send_ok(code=self.robot.get_cloud_validation_code())

        def report_play(self):
            self.send_ok(device_status=self.robot.report_play())

        def wait_status(self, status, timeout=6.0):
            mapping = {
                "idle": 0,
                "running": 16,
                "paused": 48,
                "completed": 64,
                "aborted": 128,
            }

            if status.isdigit() is False:
                st_id = mapping.get(status)
            else:
                st_id = int(status, 10)

            ttl = time() + float(timeout)

            while ttl > time():
                st = self.robot.report_play()
                if st["st_id"] == st_id:
                    self.send_ok()
                    return
                else:
                    sleep(0.2)

            self.send_error("TIMEOUT")

        def play_info(self):
            metadata, images = self.robot.play_info()

            for mime, buf in images:
                self.send_binary_begin(mime, len(buf))
                self.send_binary(buf)
            self.send_ok(**metadata)

        def config_set(self, key, *value):
            self.robot.config[key] = ' '.join(value)
            self.send_ok(key=key)

        def config_set_json(self, key, *value):
            data = pipes.quote(' '.join(value))
            self.robot.config[key] = data
            self.send_ok(key=key)

        def config_get(self, key):
            self.send_ok(key=key, value=self.robot.config[key])

        def config_del(self, key):
            del self.robot.config[key]
            self.send_ok(key=key)

        def pipe_set(self, key, *value):
            self.robot.pipe[key] = " ".join(value)
            self.send_ok(key=key)

        def pipe_get(self, key):
            self.send_ok(key=key, value=self.robot.pipe[key])

        def pipe_del(self, key):
            del self.robot.pipe[key]
            self.send_ok(key=key)

        def fetch_log(self, logname):
            flag = []

            def report(left, size):
                if not flag:
                    flag.append(1)
                    self.send_json(status="transfer", completed=0, size=size)
                self.send_json(status="transfer",
                               completed=(size - left), size=size)

            buf = BytesIO()
            mimetype = self.robot.fetch_log(logname, buf, report)
            if mimetype:
                self.send_json(status="binary", mimetype=mimetype,
                               size=buf.truncate())
                self.send_binary(buf.getvalue())
                self.send_ok()

        def fetch_laser_records(self):
            flag = []

            def report(left, size):
                if not flag:
                    flag.append(1)
                    self.send_json(status="transfer", completed=0, size=size)
                self.send_json(status="transfer",
                               completed=(size - left), size=size)

            buf = BytesIO()
            mimetype = self.robot.fetch_laser_records(buf, report)
            if mimetype:
                self.send_json(status="binary", mimetype=mimetype,
                               size=buf.truncate())
                self.send_binary(buf.getvalue())
                self.send_ok()

        def fetch_camera_calib_pictures(self, filename):
            flag = []

            def report(left, size):
                if not flag:
                    flag.append(1)
                    self.send_json(status="transfer", completed=0, size=size)
                self.send_json(status="transfer",
                               completed=(size - left), size=size)

            buf = BytesIO()
            mimetype = self.robot.fetch_camera_calib_pictures(filename, buf, report)
            if mimetype:
                self.send_json(status="binary", mimetype=mimetype,
                               size=buf.truncate())
                self.send_binary(buf.getvalue())
                self.send_ok()

        def fetch_fisheye_params(self):
            flag = []

            def report(left, size):
                if not flag:
                    flag.append(1)
                    self.send_json(status="transfer", completed=0, size=size)
                self.send_json(status="transfer",
                               completed=(size - left), size=size)

            buf = BytesIO()
            mimetype = self.robot.fetch_fisheye_params(buf, report)
            if mimetype:
                self.send_json(status="binary", mimetype=mimetype,
                               size=buf.truncate())
                self.send_binary(buf.getvalue())
                self.send_ok()

        def fetch_fisheye_3d_rotation(self):
            flag = []

            def report(left, size):
                if not flag:
                    flag.append(1)
                    self.send_json(status="transfer", completed=0, size=size)
                self.send_json(status="transfer",
                               completed=(size - left), size=size)

            buf = BytesIO()
            mimetype = self.robot.fetch_fisheye_3d_rotation(buf, report)
            if mimetype:
                self.send_json(status="binary", mimetype=mimetype,
                               size=buf.truncate())
                self.send_binary(buf.getvalue())
                self.send_ok()

        def fetch_auto_leveling_data(self, data_type):
            flag = []

            def report(left, size):
                if not flag:
                    flag.append(1)
                    self.send_json(status="transfer", completed=0, size=size)
                self.send_json(status="transfer",
                               completed=(size - left), size=size)

            buf = BytesIO()
            mimetype = self.robot.fetch_auto_leveling_data(data_type, buf, report)
            if mimetype:
                self.send_json(status="binary", mimetype=mimetype,
                               size=buf.truncate())
                self.send_binary(buf.getvalue())
                self.send_ok()

        def jsonrpc_req(self, data):
            resp = self.task.jsonrpc_req(data)
            printable = set(string.printable)
            resp = ''.join(filter(lambda x: x in printable, resp))
            data = json.loads(resp)
            self.send_ok(data=data)

        def on_pipe_task_message(self, task_type, message):
            if message == 'quit' or message == 'task quit':
                self.remove_task_socket(task_type)
                self.task_quit()
                return
            socket: PipeSocket = self.get_task_socket(task_type)
            if not socket:
                self.send_error('TASK_SOCKET_CLOSED')
                self.task_quit()
                return
            return socket

        def on_raw_message(self, message):
            socket = self.on_pipe_task_message('raw', message)
            if socket:
                if message == 'raw home':
                    socket.send('$H\n'.encode())
                else:
                    socket.send(message.encode() + b'\n')

        def on_sub_task_message(self, message):
            if message == 'quit' or message == 'task quit':
                self.task_quit()
                return
            # TODO: add no shlex.split version?
            if message.startswith('jsonrpc_req '):
                args = shlex.split(message)
                self.jsonrpc_req(args[1])
                return
            resp = self.robot._backend.make_cmd(message.encode())
            task_name = getattr(self._task, 'task_name', self._task.__class__)
            logger.info('%s: <= %s', task_name, resp)
            self.send_ok(data=resp)

    class DirtyLayer(ControlApi):
        __last_command = None

        # Front require command string append at response, override on_command
        # to record command.
        def on_command(self, message):
            if message != "ping":
                self.__last_command = message

            super().on_command(message)

        def send_ok(self, **kw):
            # Override send_ok and send front request string at response.
            # Request from norman.
            if self.__last_command:
                if self.__last_command.startswith("file ls "):
                    kw["cmd"] = "ls"
                elif self.__last_command.startswith("play select"):
                    kw["cmd"] = "select"
                elif self.__last_command.startswith("file mkdir"):
                    kw["cmd"] = "mkdir"
                elif self.__last_command.startswith("file rmdir"):
                    kw["cmd"] = "rmdir"
                elif self.__last_command.startswith("file cpfile"):
                    kw["cmd"] = "cpfile"
                else:
                    kw["cmd"] = self.__last_command

            # Pop prog when play status id is completed. Request from proclaim.
            if "device_status" in kw:
                if kw["device_status"]["st_id"] == 64:
                    kw["device_status"].pop("prog", None)


            super().send_ok(**kw)

    return DirtyLayer


class PipeSocket(object):
    """This class pipe data from socket connected to device to websocket connected to frontend"""
    _task_type = 'pipe'

    def __init__(self, sock, ws, task = 'pipe'):
        self.sock = sock
        self.ws = ws
        self._task_type = task

    def fileno(self):
        return self.sock.fileno()

    def send(self, data):
        self.sock.send(data)

    def on_read(self):
        buf = self.sock.recv(128)
        if buf:
            logger.info('%s: <= %s' % (self._task_type, buf.decode("ascii", "replace")))
            self.ws.send_json(status=self._task_type,
                              text=buf.decode("ascii", "replace"))
        else:
            self.ws.rlist.remove(self)
            self.ws.send_fatal("DISCONNECTED")
