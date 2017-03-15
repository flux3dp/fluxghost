
from errno import EPIPE
from time import time, sleep
from io import BytesIO
import logging
import socket
import shlex

from fluxclient.device.host2host_usb import FluxUSBError
from fluxclient.robot.errors import RobotError, RobotSessionError
from fluxclient.utils.version import StrictVersion
from fluxclient.fcode.g_to_f import GcodeToFcode

from .control_base import control_base_mixin

logger = logging.getLogger("API.CONTROL")


STAGE_DISCOVER = '{"status": "connecting", "stage": "discover"}'
STAGE_ROBOT_CONNECTING = '{"status": "connecting", "stage": "connecting"}'
STAGE_CONNECTED = '{"status": "connected"}'
STAGE_TIMEOUT = '{"status": "error", "error": "TIMEOUT"}'


def control_api_mixin(cls):
    class ControlApi(control_base_mixin(cls)):
        _task = None
        raw_sock = None

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
                "update_mbfw": self.update_mbfw,

                "deviceinfo": self.deviceinfo,
                "cloud_validate_code": self.cloud_validate_code,
                "wait_status": self.wait_status,
                "kick": self.kick,

                "file": {
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

                "maintain": {
                    "wait_head": self.maintain_wait_head,
                    "load_filament": self.maintain_load_filament,
                    "unload_filament": self.maintain_unload_filament,
                    "calibrating": self.maintain_calibrate,
                    "calibrate": self.maintain_calibrate,
                    "zprobe": self.maintain_zprobe,
                    "headinfo": self.maintain_headinfo,
                    "set_heater": self.maintain_set_heater,
                    "diagnosis_sensor": self.maintain_diagnosis_sensor,
                    "diagnosis": self.maintain_diagnosis,
                    "headstatus": self.maintain_headstatus,
                    "home": self.maintain_home,
                    "update_hbfw": self.maintain_update_hbfw
                },

                "config": {
                    "set": self.config_set,
                    "get": self.config_get,
                    "del": self.config_del
                },

                "play": {
                    "select": self.select_file,
                    "start": self.start_play,
                    "info": self.play_info,
                    "report": self.report_play,
                    "pause": self.pause_play,
                    "resume": self.resume_play,
                    "abort": self.abort_play,
                    "toolhead": {
                        "operation": self.set_toolhead_operating,
                        "standby": self.set_toolhead_standby,
                        "heater": self.set_toolhead_heater,
                    },
                    "load_filament": self.load_filamend_in_play,
                    "unload_filament": self.unload_filamend_in_play,
                    "press_button": self.press_button_in_play,
                    "quit": self.quit_play
                },

                "scan": {
                    "oneshot": self.scan_oneshot,
                    "scanimages": self.scanimages,
                    "backward": self.scan_backward,
                    "forward": self.scan_forward,
                    "step": self.scan_step,
                    "laser": self.scan_lasr,
                },

                "task": {
                    "maintain": self.task_begin_maintain,
                    "scan": self.task_begin_scan,
                    "raw": self.task_begin_raw,
                    "quit": self.task_quit,
                },

                "fetch_log": self.fetch_log
            }

        @property
        def task(self):
            if not self._task:
                raise RuntimeError("OPERATION_ERROR")
            return self._task

        @task.setter
        def task(self, val):
            self._task = val

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

            if self.raw_sock:
                self.on_raw_message(message)
                return

            args = shlex.split(message)

            try:
                if self.invoke_command(self.cmd_mapping, args):
                    pass
                else:
                    logger.warn("Unknow Command: %s" % message)
                    self.send_error("L_UNKNOWN_COMMAND")

            except RobotError as e:
                logger.debug("RobotError%s [error_symbol=%s]", repr(e.args),
                             e.error_symbol)
                self.send_error(e.error_symbol[0], symbol=e.error_symbol)

            except RobotSessionError as e:
                logger.warning("RobotSessionError%s [error_symbol=%s]",
                               repr(e.args), e.error_symbol)
                self.send_fatal(*e.error_symbol)

            except FluxUSBError as e:
                logger.exception("USB Error%s [error_symbol=%s]",
                                 repr(e.args), e.symbol)
                self.send_fatal(*e.symbol)
            except RuntimeError as e:
                logger.debug("RuntimeError Error%s", repr(e.args))
                self.send_error(*e.args)

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
                self.send_error("L_UNKNOWN_ERROR", repr(e.__class__))

            except socket.error as e:
                if e.args[0] == EPIPE:
                    self.send_fatal("DISCONNECTED", repr(e.__class__))
                else:
                    logger.exception("Unknow socket error")
                    self.send_fatal("L_UNKNOWN_ERROR", repr(e.__class__))

            except Exception as e:
                logger.exception("Unknow error while process text")
                self.send_error("L_UNKNOWN_ERROR", repr(e.__class__))

        def kick(self):
            self.robot.kick()
            self.send_ok()

        def list_file(self, location=""):
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

        def select_file(self, file):
            path = file if file.startswith("/") else "/" + file
            self.robot.select_file(path)
            self.send_ok(path=path)

        def fileinfo(self, file):
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
                self.send_error("NOT_SUPPORT", symbol=["NOT_SUPPORT"])

        def rmdir(self, file):
            path = file if file.startswith("/") else "/" + file
            if path.startswith("/SD/"):
                self.robot.rmdir(path)
                self.send_ok(path=path)
            else:
                self.send_error("NOT_SUPPORT", symbol=["NOT_SUPPORT"])

        def rmfile(self, file):
            path = file if file.startswith("/") else "/" + file
            if path.startswith("/SD/"):
                self.robot.rmfile(path)
                self.send_json(status="ok", path=path)
            else:
                self.send_error("NOT_SUPPORT", symbol=["NOT_SUPPORT"])

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

            elif mimetype == "application/fcode":
                self.simple_binary_transfer(
                    self.robot.yihniwimda_upload_stream, mimetype, size,
                    upload_to=upload_to, cb=self.send_ok)

            else:
                self.send_text('{"status":"error", "error": "FCODE_ONLY"}')
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
                    self.send_error(e.error_symbol[0], symbol=e.error_symbol)
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

        def pause_play(self):
            self.robot.pause_play()
            self.send_ok()

        def resume_play(self):
            self.robot.resume_play()
            self.send_ok()

        def abort_play(self):
            self.robot.abort_play()
            self.send_ok()

        def set_toolhead_operating(self):
            self.robot.set_toolhead_operating_in_play()
            self.send_ok()

        def set_toolhead_standby(self):
            self.robot.set_toolhead_standby_in_play()
            self.send_ok()

        def set_toolhead_heater(self, index, temp):
            self.robot.set_toolhead_heater_in_play(float(temp), int(index))
            self.send_ok()

        def load_filamend_in_play(self, index):
            self.robot.load_filament_in_play(int(index))
            self.send_ok()

        def unload_filamend_in_play(self, index):
            self.robot.unload_filament_in_play(int(index))
            self.send_ok()

        def press_button_in_play(self):
            self.robot.press_button_in_play()
            self.send_ok()

        def quit_play(self):
            self.robot.quit_play()
            self.send_ok()

        def maintain_update_hbfw(self, mimetype, ssize):
            size = int(ssize)

            def update_cb(swap):
                def nav_cb(robot, *args):
                    # >>>>
                    if args[0] == "UPLOADING":
                        self.send_json(status="uploading", sent=int(args[1]))
                    elif args[0] == "WRITE":
                        self.send_json(status="operating",
                                       stage=["UPDATE_THFW", "WRITE"],
                                       written=size - int(args[1]))

                        self.send_json(status="update_hbfw", stage="WRITE",
                                       written=size - int(args[1]))
                    else:
                        self.send_json(status="operating",
                                       stage=["UPDATE_THFW", args[0]])

                        self.send_json(status="update_hbfw", stage=args[0])
                    # <<<<
                size = swap.truncate()
                swap.seek(0)

                try:
                    self.task.update_hbfw(swap, size, nav_cb)
                    self.send_ok()
                except RobotError as e:
                    self.send_error(e.error_symbol[0], symbol=e.error_symbol)
                except Exception as e:
                    logger.exception("ERR")
                    self.send_fatal("L_UNKNOWN_ERROR", e.args)

            self.simple_binary_receiver(size, update_cb)

        def task_begin_scan(self):
            self.task = self.robot.scan()
            self.send_ok(task="scan")

        def task_begin_maintain(self):
            self.task = self.robot.maintain()
            self.send_ok(task="maintain")

        def task_begin_raw(self):
            self.task = self.robot.raw()
            self.raw_sock = RawSock(self.task.sock, self)
            self.rlist.append(self.raw_sock)
            self.send_ok(task="raw")

        def task_quit(self):
            self.task.quit()
            self.task = None
            self.send_ok(task="")

        def maintain_home(self):
            self.task.home()
            self.send_ok()

        def maintain_calibrate(self, *args):
            def callback(robot, *args):
                try:
                    if args[0] == "POINT":
                        self.send_json(status="operating",
                                       stage=["CALIBRATING"], pos=int(args[1]))
                    elif args[0] == "CTRL" and args[1] == "POINT":
                        self.send_json(status="operating",
                                       stage=["CALIBRATING"], pos=int(args[2]))
                    elif args[0] == "DEBUG":
                        self.send_json(status="debug", log=" ".join(args[1:]))
                    else:
                        self.send_json(status="debug", args=args)
                except Exception:
                    logger.exception("Error during calibration cb")

            if "clean" in args:
                ret = self.task.calibration(process_callback=callback,
                                            clean=True)
            else:
                ret = self.task.calibration(process_callback=callback)
            self.send_json(status="ok", data=ret,
                           error=(max(*ret) - min(*ret)))

        def maintain_zprobe(self, *args):
            def callback(robot, *args):
                if args[0] == "CTRL" and args[1] == "ZPROBE":
                    self.send_json(status="operating",
                                   stage=["ZPROBE"])
                elif args[0] == "DEBUG":
                    self.send_json(status="debug", log=" ".join(args[1:]))
                else:
                    self.send_json(status="debug", args=args)

            if len(args) > 0:
                ret = self.task.manual_level(float(args[0]))
            else:
                ret = self.task.zprobe(process_callback=callback)

            self.send_json(status="ok", data=ret)

        def maintain_load_filament(self, index, temp):
            def nav(robot, *args):
                try:
                    stage = args[0]
                    if stage == "HEATING":
                        self.send_json(status="operating", stage=["HEATING"],
                                       temperature=float(args[1]))
                    elif stage == "LOADING":
                        self.send_json(status="operating",
                                       stage=["FILAMENT", "LOADING"])
                    elif stage == "WAITING":
                        self.send_json(status="operating",
                                       stage=["FILAMENT", "WAITING"])
                except Exception:
                    logger.exception("Error during load filament cb")

            self.task.load_filament(int(index), float(temp), nav)
            self.send_ok()

        def maintain_unload_filament(self, index, temp):
            def nav(robot, *args):
                try:
                    stage = args[0]
                    if stage == "HEATING":
                        self.send_json(status="operating", stage=["HEATING"],
                                       temperature=float(args[1]))
                    else:
                        self.send_json(status="operating",
                                       stage=["FILAMENT", stage])
                except Exception:
                    logger.exception("Error during unload filament cb")
            self.task.unload_filament(int(index), float(temp), nav)
            self.send_ok()

        def maintain_headinfo(self):
            info = self.task.head_info()
            if "head_module" not in info:
                if "TYPE" in info:
                    info["head_module"] = info.get("TYPE")
                elif "module" in info:
                    info["head_module"] = info.get("module")

            if "version" not in info:
                info["version"] = info["VERSION"]
            self.send_ok(**info)

        def maintain_set_heater(self, index, temperature):
            self.task.set_heater(int(index), float(temperature))
            self.send_ok()

        def maintain_diagnosis_sensor(self):
            result = self.task.diagnosis_sensor()
            self.send_ok(sensor=result)

        def maintain_diagnosis(self, option):
            self.send_ok(ret=self.task.diagnosis(option))

        def maintain_headstatus(self):
            status = self.task.head_status()
            self.send_ok(**status)

        def maintain_wait_head(self, head_type, timeout=6.0):
            ttl = time() + float(timeout)

            while ttl > time():
                st = self.task.head_status()
                if st["module"] == head_type:
                    self.send_ok()
                else:
                    sleep(0.2)

            self.send_error("TIMEOUT", symbol=["TIMEOUT"])

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

            self.send_error("TIMEOUT", symbol=["TIMEOUT"])

        def scan_oneshot(self):
            images = self.task.oneshot()
            for mimetype, buf in images:
                self.send_binary_buffer(mimetype, buf)
            self.send_ok()

        def scanimages(self):
            images = self.task.scanimages()
            for mimetype, buf in images:
                self.send_binary_buffer(mimetype, buf)
            self.send_ok()

        def scan_forward(self):
            self.task.forward()
            self.send_ok()

        def scan_backward(self):
            self.task.backward()
            self.send_ok()

        def scan_step(self, length):
            self.task.step_length(float(length))
            self.send_ok()

        def scan_lasr(self, flag):
            if flag.isdigit():
                dflag = int(flag)
                self.task.laser(dflag & 1, dflag & 2)
            else:
                self.task.laser(False, False)
            self.send_ok()

        def play_info(self):
            metadata, images = self.robot.play_info()

            for mime, buf in images:
                self.send_binary_begin(mime, len(buf))
                self.send_binary(buf)
            self.send_ok(**metadata)

        def config_set(self, key, *value):
            self.robot.config[key] = " ".join(value)
            self.send_ok(key=key)

        def config_get(self, key):
            self.send_ok(key=key, value=self.robot.config[key])

        def config_del(self, key):
            del self.robot.config[key]
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

        def on_raw_message(self, message):
            if message == "quit" or message == "task quit":
                self.rlist.remove(self.raw_sock)
                self.raw_sock = None
                self.task.quit()
                self.send_text('{"status": "ok", "task": ""}')
            else:
                self.raw_sock.sock.send(message.encode() + b"\n")

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
                if self.__last_command.startswith("file ls"):
                    kw["cmd"] = "ls"
                elif self.__last_command.startswith("play select"):
                    kw["cmd"] = "select"
                elif self.__last_command.startswith("file mkdir"):
                    kw["cmd"] = "mkdir"
                elif self.__last_command.startswith("file rmdir"):
                    kw["cmd"] = "rmdir"
                elif self.__last_command.startswith("file cpfile"):
                    kw["cmd"] = "cpfile"
                elif self.__last_command.startswith("maintain headinfo"):
                    kw["cmd"] = "headinfo"
                else:
                    kw["cmd"] = self.__last_command

            # Pop prog when play status id is completed. Request from proclaim.
            if "device_status" in kw:
                if kw["device_status"]["st_id"] == 64:
                    kw["device_status"].pop("prog", None)

            super().send_ok(**kw)

    return DirtyLayer


class RawSock(object):
    def __init__(self, sock, ws):
        self.sock = sock
        self.ws = ws

    def fileno(self):
        return self.sock.fileno()

    def on_read(self):
        buf = self.sock.recv(128)
        if buf:
            self.ws.send_json(status="raw",
                              text=buf.decode("ascii", "replace"))
        else:
            self.ws.rlist.remove(self)
            self.ws.send_fatal("DISCONNECTED")
