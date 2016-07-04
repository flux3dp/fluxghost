
from time import time
import logging

from fluxclient import SUPPORT_PCL
from fluxclient.scanner.scan_settings import ScanSetting
from fluxclient.scanner.pc_process import PcProcess
from .misc import BinaryUploadHelper

logger = logging.getLogger("API.3DSCAN-MODELING")


def scan_modeling_api_mixin(cls):
    class ScannModelingApi(cls):
        def __init__(self, *args):
            super().__init__(*args)
            # ##################################
            SIMULATE = False
            # ##################################
            if not SIMULATE:
                self.m_pc_process = PcProcess(ScanSetting())
                logger.debug('using PcProcess')
            if SIMULATE:
                self.m_pc_process = PcProcessNoPCL()
                logger.debug('using PcProcessNoPCL()')
            self.cmd_mapping = {
                'upload': [self._begin_upload],
                'cut': [self.cut],
                'delete_noise': [self.delete_noise],
                'dump': [self.dump],
                'export': [self.export],
                'apply_transform': [self.apply_transform],
                'merge': [self.merge],
                'auto_alignment': [self.auto_alignment],
                'set_params': [self.set_params],
                'import_file': [self.import_file],
                'export_threading': [self.export_threading],
                'export_collect': [self.export_collect],
            }

        def _begin_upload(self, params):  # name, left_len, right_len="0"
            splited_params = params.split()
            try:
                name = splited_params[0]
                s_left_len = splited_params[1]
                s_right_len = splited_params[2] if len(splited_params) > 2 else "0"

                llen = int(s_left_len)
                rlen = int(s_right_len)
                totel_length = (llen + rlen) * 24
            except ValueError:
                raise RuntimeError("BAD_PARAM_TYPE", "upload param error")
            logger.debug('uploading {}, L:{}, R:{}, time:{}'.format(name, s_left_len, s_right_len, time()))
            helepr = BinaryUploadHelper(totel_length, self._end_upload,
                                        1, name, llen, rlen)
            self.set_binary_helper(helepr)
            self.send_continue()

        def _end_upload(self, buf, flag, name, *args):
            o_flag = True
            if flag == 1:
                left_len, right_len = args
                left_points = buf[:left_len * 24]
                right_points = buf[left_len * 24:]
                self.m_pc_process.upload(name, left_points, right_points, left_len, right_len)
            elif flag == 2:
                filetype = args[0]
                o_flag, message = self.m_pc_process.import_file(name, buf, filetype)
            if o_flag:
                self.send_ok()
            else:
                self.send_error(message)

        def cut(self, params):
            name_in, name_out, mode, direction, value = params.split()
            value = float(value)
            direction = direction[0] == 'T'
            self.m_pc_process.cut(name_in, name_out, mode, direction, value)
            self.send_ok()

        def merge(self, params):
            name_base, name_2, name_out = params.split()
            self.m_pc_process.merge(name_base, name_2, name_out)
            self.send_ok()

        def apply_transform(self, params):
            name_in, x, y, z, rx, ry, rz, name_out = params.split()
            x = float(x)
            y = float(y)
            z = float(z)
            rx = float(rx)
            ry = float(ry)
            rz = float(rz)
            self.m_pc_process.apply_transform(name_in, x, y, z, rx, ry, rz, name_out)
            self.send_ok()

        def auto_alignment(self, params):

            name_base, name_2, name_out = params.split()
            if self.m_pc_process.auto_alignment(name_base, name_2, name_out):
                self.send_ok()
            else:
                self.send_text('{"status": "fail"')

        def delete_noise(self, params):
            if not SUPPORT_PCL:
                self.send_error('No pcl')
                return
            logger.debug(params)
            name_in, name_out, r = params.split()
            r = float(r)
            self.m_pc_process.delete_noise(name_in, name_out, r)
            self.send_ok()

        def dump(self, params):
            name = params
            len_L, len_R, buffer_data = self.m_pc_process.dump(name)
            self.send_text('{{"status": "continue", "left": {}, "right": {}}}'.format(len_L, len_R))
            self.send_binary(buffer_data)
            self.send_ok()
            logger.debug('dump %s done' % (name))

        def export(self, params):
            """
            should be de deprecated
            """
            name, file_foramt = params.split()
            buf = self.m_pc_process.export(name, file_foramt)
            self.send_text('{{"status": "continue", "length": {}}}'.format(len(buf)))
            self.send_binary(buf)
            self.send_ok()
            logger.debug('export {} as .{} file done'.format(name, file_foramt))

        def export_threading(self, params):
            name, file_foramt = params.split()
            collect_name = self.m_pc_process.export_threading(name, file_foramt)
            self.send_text('{{"status": "ok", "collect_name": "{}"}}'.format(collect_name))
            logger.debug('export {} as .{} file in thread'.format(name, file_foramt))

        def export_collect(self, params):
            collect_name = params

            buf = self.m_pc_process.export_collect(collect_name)
            if buf:
                self.send_text('{{"status": "continue", "length": {}}}'.format(len(buf)))
                self.send_binary(buf)
                self.send_ok()
            elif buf == 'key error':
                self.send_error('{} key not exist'.format(key))
            else:
                self.send_text('{"status": "computing"}')

        def import_file(self, params):
            name, filetype, file_length = params.split()
            helepr = BinaryUploadHelper(int(file_length), self._end_upload, 2, name, filetype)
            self.set_binary_helper(helepr)
            self.send_continue()

        def set_params(self, params):
            key, value = params.split()
            if key in ['NeighborhoodDistance', 'CloseBottom', 'CloseTop', 'SegmentationDistance', 'NoiseNeighbors']:
                setattr(self.m_pc_process.settings, key, float(value))
                self.send_ok()
            else:
                self.send_error('{} key not exist'.format(key))
    return ScannModelingApi
