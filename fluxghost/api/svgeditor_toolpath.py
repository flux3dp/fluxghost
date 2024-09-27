import base64
import io
import json
import logging
import math
import threading
import urllib.parse
import traceback
from datetime import datetime

from PIL import Image

from fluxclient.toolpath.svgeditor_factory import SvgeditorImage, SvgeditorFactory

from fluxclient.toolpath.toolpath import svgeditor2taskcode, gcode2fcode
from fluxclient.toolpath import FCodeV1MemoryWriter, FCodeV2MemoryWriter, GCodeMemoryWriter
from fluxclient import __version__

import fluxsvg

from fluxghost.utils.username import get_username
from .svg_toolpath import svg_base_api_mixin
from .misc import BinaryUploadHelper, OnTextMessageMixin

logger = logging.getLogger("API.SVGEDITOR")

def laser_svgeditor_api_mixin(cls):
    class LaserSvgeditorApi(OnTextMessageMixin, svg_base_api_mixin(cls)):
        def __init__(self, *args):
            self.pixel_per_mm = 10
            self.svg_image = None
            self.loop_compensation = 0.0
            self.is_task_interrupted = False
            self.curve_engraving_detail = None
            super().__init__(*args)
            self.cmd_mapping = {
                'upload_plain_svg': [self.cmd_upload_plain_svg],
                'divide_svg': [self.divide_svg],
                'divide_svg_by_layer': [self.divide_svg_by_layer],
                'svgeditor_upload': [self.cmd_svgeditor_upload],
                'go': [self.cmd_go],
                'g2f': [self.cmd_g2f],
                'set_params': [self.cmd_set_params],
                'interrupt': [self.cmd_interrupt],
            }

        def cmd_set_params(self, params):
            key, value = params.split()
            logger.info('setting parameter %r = %r', key, value)
            if not self.set_param(key, value):
                if key == 'loop_compensation':
                    self.loop_compensation = max(0, float(value))
                elif key == 'curve_engraving':
                    try:
                        curve_engraving_detail = json.loads(value)
                        self.curve_engraving_detail = curve_engraving_detail
                    except Exception:
                        logger.exception('Invalid curve_engraving value')
                        self.send_json(status='error', message='Invalid curve_engraving value')
                elif key in ('shading', 'one_way', 'calibration'):
                    pass
                else:
                    self.send_json(status='error', message='Unknown parameter %s' % key)
            self.send_ok()

        def divide_svg(self, params):
            params = params.split()
            divide_params = {}
            for i, param in enumerate(params):
                if param == '-s':
                    divide_params['scale'] = float(params[i+1])
            self.plain_svg = self.plain_svg.replace(b'encoding="UTF-16"', b'encoding="utf-8"')
            self.plain_svg = self.plain_svg.replace(b'encoding="utf-16"', b'encoding="utf-8"')
            try:
                result = fluxsvg.divide(self.plain_svg, params=divide_params, loop_compensation=self.loop_compensation)

                self.send_json(name="strokes", length=result['strokes'].getbuffer().nbytes)
                self.send_binary(result['strokes'].getbuffer())
                if result['bitmap'] is None:
                    self.send_json(name="bitmap", length=0)
                    self.send_binary(b"")
                else:
                    self.send_json(name="bitmap", length=result['bitmap'].getbuffer().nbytes, offset=result['bitmap_offset'])
                    self.send_binary(result['bitmap'].getbuffer())
                self.send_json(name="colors", length=result['colors'].getbuffer().nbytes)
                self.send_binary(result['colors'].getbuffer())
                self.send_ok()
            except Exception as e:
                traceback_info = traceback.extract_tb(e.__traceback__)
                file_name, line_number, _, _ = traceback_info[-1]
                self.send_json(status='Error', message='{}\n{}, line: {}'.format(str(e), file_name, line_number))
                raise e

        def divide_svg_by_layer(self, params):
            params = params.split()
            divide_params = {}
            for i, param in enumerate(params):
                if param == '-s':
                    divide_params['scale'] = float(params[i+1])
            self.plain_svg = self.plain_svg.replace(b'encoding="UTF-16"', b'encoding="utf-8"')
            self.plain_svg = self.plain_svg.replace(b'encoding="utf-16"', b'encoding="utf-8"')
            try:
                result = fluxsvg.divide_by_layer(self.plain_svg, params=divide_params, loop_compensation=self.loop_compensation)
                if 'nolayer' in result:
                    self.send_json(name="nolayer", length=result['nolayer'].getbuffer().nbytes)
                    self.send_binary(result['nolayer'].getbuffer())
                if result['bitmap'] is None:
                    self.send_json(name="bitmap", length=0)
                    self.send_binary(b"")
                else:
                    self.send_json(name="bitmap", length=result['bitmap'].getbuffer().nbytes, offset=result['bitmap_offset'])
                    self.send_binary(result['bitmap'].getbuffer())
                for key, item in result.items():
                    if key == 'bitmap_offset':
                        continue
                    if key == 'bitmap':
                        if item is None:
                            self.send_json(name='bitmap', length=0)
                            self.send_binary(b"")
                        else:
                            self.send_json(name='bitmap', length=item.getbuffer().nbytes, offset=result['bitmap_offset'])
                            self.send_binary(item.getbuffer())
                    else:
                        self.send_json(name=key, length=item.getbuffer().nbytes)
                        self.send_binary(item.getbuffer())
                self.send_ok()
            except Exception as e:
                traceback_info = traceback.extract_tb(e.__traceback__)
                file_name, line_number, _, _ = traceback_info[-1]
                self.send_json(status='Error', message='{}\n{}, line: {}'.format(str(e), file_name, line_number))
                raise e


        def cmd_svgeditor_upload(self, params):
            # clear previous data
            self.curve_engraving_detail = None
            svgeditor_image_params = {
                'loop_compensation': self.loop_compensation,
                'hardware': 'beambox',
                'rotary_enabled': False,
            }

            def progress_callback(prog):
                self.send_progress("Analyzing SVG - " + str(round(prog * 100, 2)) + "%", prog)

            def generate_svgeditor_image(buf, name, thumbnail_length):
                thumbnail = buf[:thumbnail_length]
                svg_data = buf[thumbnail_length:]
                svg_image = SvgeditorImage(thumbnail, svg_data, self.pixel_per_mm,
                                            progress_callback=progress_callback,
                                            check_interrupted=self.check_interrupted,
                                            **svgeditor_image_params)
                self.svg_image = svg_image

            def upload_callback(buf, name, thumbnail_length):
                if self.has_binary_helper():
                    self.set_binary_helper(None)
                try:
                    generate_svgeditor_image(buf, name, thumbnail_length)
                    if self.check_interrupted():
                        logger.info('svgeditor_upload interrupted')
                        return
                    self.send_ok()
                except Exception as e:
                    logger.exception("Load SVG Error")
                    logger.exception(str(e))
                    traceback_info = traceback.extract_tb(e.__traceback__)
                    file_name, line_number, _, _ = traceback_info[-1]
                    self.send_json(status='Error', message='{}\n{}, line: {}'.format(str(e), file_name, line_number))
                    raise e

            logger.info('svg_editor')
            self.is_task_interrupted = False
            params = params.split()
            name = params[0]
            file_length = params[1]
            thumbnail_length = params[2]
            self.factory_kwargs = {}

            for i, param in enumerate(params):
                if param == '-bb2' or param == '-hexa':
                    svgeditor_image_params['hardware'] = 'hexa'
                elif param == '-pro':
                    svgeditor_image_params['hardware'] = 'beambox-pro'
                elif param == '-beamo':
                    svgeditor_image_params['hardware'] = 'beamo'
                elif param == '-ado1':
                    svgeditor_image_params['hardware'] = 'ador'
                elif param == '-fbb2':
                    svgeditor_image_params['hardware'] = 'fbb2'
                elif param == '-ldpi':
                    self.pixel_per_mm = 5
                elif param == '-mdpi':
                    self.pixel_per_mm = 10
                elif param == '-hdpi':
                    self.pixel_per_mm = 20
                elif param == '-udpi':
                    self.pixel_per_mm = 50
                    self.factory_kwargs['pixel_per_mm_x'] = 20
                elif param == '-dpi':
                    try:
                        dpi = int(params[i+1])
                        self.pixel_per_mm = round(dpi / 25.4)
                        if self.pixel_per_mm > 20:
                            self.factory_kwargs['pixel_per_mm_x'] = 20
                    except Exception:
                        pass
                elif param == '-spin':
                    svgeditor_image_params['rotary_enabled'] = True
                    self.factory_kwargs['rotary_enabled'] = True

            try:
                file_length, thumbnail_length = map(int, (file_length, thumbnail_length))
                helper = BinaryUploadHelper(
                        file_length, upload_callback, name, thumbnail_length)

                self.set_binary_helper(helper)
                self.send_json(status="continue")
            except Exception as e:
                traceback_info = traceback.extract_tb(e.__traceback__)
                file_name, line_number, _, _ = traceback_info[-1]
                self.send_json(status='Error', message='{}\n{}, line: {}'.format(str(e), file_name, line_number))
                raise e

        def cmd_upload_plain_svg(self, params):
            def upload_callback(buf, name):
                if self.has_binary_helper():
                    self.set_binary_helper(None)
                #todo divide buf as svg
                self.plain_svg = buf
                self.send_ok()

            logger.info('svg_editor')

            name, file_length = params.split()
            file_length = int(file_length)
            helper = BinaryUploadHelper(
                    file_length, upload_callback, name)

            self.set_binary_helper(helper)
            self.send_json(status="continue")

        def prepare_factory(self):
            factory = SvgeditorFactory(self.pixel_per_mm, loop_compensation=self.loop_compensation, **self.factory_kwargs)
            factory.add_image(self.svg_image)
            return factory

        def cmd_g2f(self, params_str):
            def progress_callback(prog):
                prog = math.floor(prog * 500) / 500
                self.send_progress("Calculating Toolpath " + str(round(prog * 100, 2)) + "%", prog)
            def upload_callback(buf, thumbnail_length):
                def process_thumbnail(base64_thumbnail: str):
                    _, data = base64_thumbnail.split(b',')
                    data = Image.open(io.BytesIO(base64.b64decode(data)))
                    bytes = io.BytesIO()
                    data.save(bytes, 'png')
                    return bytes.getvalue()

                if self.has_binary_helper():
                    self.set_binary_helper(None)
                #todo divide buf as svg
                thumbnail = process_thumbnail(buf[:thumbnail_length])
                self.gcode_string = buf[thumbnail_length:]
                self.send_ok()
                send_fcode = True
                try:
                    self.send_progress('Initializing', 0.03)

                    self.fcode_metadata.update({
                        'CREATED_AT': datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
                        'AUTHOR': urllib.parse.quote(get_username()),
                        'SOFTWARE': 'fluxclient-%s-BS' % __version__,
                    })
                    writer = FCodeV1MemoryWriter('LASER', self.fcode_metadata,
                                                 (thumbnail, ))
                    default_travel_speed = 7500

                    gcode2fcode(writer, self.gcode_string,
                                    travel_speed=default_travel_speed,
                                    progress_callback=progress_callback,
                                    check_interrupted=self.check_interrupted)

                    writer.terminated()

                    if self.check_interrupted():
                        logger.info('cmd g2f interrupted')
                        return

                    output_binary = writer.get_buffer()
                    time_need = float(writer.get_metadata().get(b"TIME_COST", 0))

                    traveled_dist = float(writer.get_metadata().get(b"TRAVEL_DIST", 0))
                    self.send_progress('Finishing', 1.0)

                    if send_fcode:
                        self.send_json(status="complete", length=len(output_binary), time=time_need, traveled_dist=traveled_dist)
                        self.send_binary(output_binary)
                    else:
                        output_file = open("/var/gcode/userspace/temp.fc", "wb")
                        output_file.write(output_binary)
                        output_file.close()
                        self.send_json(status="complete", file="/var/gcode/userspace/temp.fc")
                    logger.info("G2F Processed")
                except Exception as e:
                    traceback_info = traceback.extract_tb(e.__traceback__)
                    file_name, line_number, _, _ = traceback_info[-1]
                    self.send_json(status='Error', message='{}\n{}, line: {}'.format(str(e), file_name, line_number))
                    raise e

            logger.info('task preview: gcode to fcode')
            file_length, thumbnail_length = map(int, params_str.split())

            helper = BinaryUploadHelper(
                    file_length, upload_callback, thumbnail_length)

            self.set_binary_helper(helper)
            self.send_json(status="continue")

        def cmd_go(self, params_str):
            def progress_callback(prog):
                prog = math.floor(prog * 500) / 500
                self.send_progress("Calculating Toolpath " + str(round(prog * 100, 2)) + "%", prog)

            logger.info('Calling laser svgeditor')
            self.is_task_interrupted = False
            output_fcode = True
            params = params_str.split()
            hardware_name = 'beambox'
            send_fcode = True

            svgeditor2taskcode_kwargs = {'travel_speed': 7500, 'path_travel_speed': 7500, 'acc': 4000}
            svgeditor2taskcode_kwargs['curve_engraving'] = self.curve_engraving_detail
            clip_rect = None
            is_rotary_task = False
            start_with_home = True
            fcode_version = 1

            for i, param in enumerate(params):
                if param == '-hexa' or param == '-bb2':
                    hardware_name = 'hexa'
                elif param == '-pro':
                    hardware_name = 'beambox-pro'
                elif param == '-beamo':
                    hardware_name = 'beamo'
                elif param == '-ado1':
                    hardware_name = 'ador'
                    svgeditor2taskcode_kwargs['path_travel_speed'] = 3600
                    fcode_version = 2
                elif param == '-fbb2':
                    hardware_name = 'fbb2'
                    fcode_version = 2
                elif param == '-film':
                    self.fcode_metadata["CONTAIN_PHONE_FILM"] = '1'
                elif param == '-spin':
                    val = float(params[i+1])
                    svgeditor2taskcode_kwargs['spinning_axis_coord'] = val
                    if val > 0:
                        self.fcode_metadata['ROTARY'] = '1'
                        is_rotary_task = True
                elif param == '-rotary-y-ratio':
                    svgeditor2taskcode_kwargs['rotary_y_ratio'] = float(params[i+1])
                elif param == '-blade':
                    svgeditor2taskcode_kwargs['blade_radius'] = float(params[i+1])
                elif param == '-precut':
                    svgeditor2taskcode_kwargs['precut_at'] = [float(j) for j in params[i+1].split(',')]
                elif param == '-prespray':
                    svgeditor2taskcode_kwargs['prespray'] = [float(j) for j in params[i+1].split(',')]
                elif param == '-temp':
                    send_fcode = False
                elif param == '-gc':
                    output_fcode = False
                elif param == '-af':
                    svgeditor2taskcode_kwargs['enable_autofocus'] = True
                    try:
                        svgeditor2taskcode_kwargs['z_offset'] = float(params[i+1])
                    except Exception:
                        pass
                elif param == '-fg':
                    svgeditor2taskcode_kwargs['support_fast_gradient'] = True
                elif param == '-mfg':
                    svgeditor2taskcode_kwargs['mock_fast_gradient'] = True
                elif param == '-vsc':
                    svgeditor2taskcode_kwargs['has_vector_speed_constraint'] = True
                elif param == '-diode':
                    svgeditor2taskcode_kwargs['support_diode'] = True
                    svgeditor2taskcode_kwargs['diode_offset'] = [float(j) for j in params[i+1].split(',')]
                elif param == '-diode-owe':
                    svgeditor2taskcode_kwargs['diode_one_way_engraving'] = True
                elif param == '-acc':
                    svgeditor2taskcode_kwargs['acc'] = float(params[i+1])
                elif param == '-min-speed':
                    svgeditor2taskcode_kwargs['min_speed'] = float(params[i+1])
                elif param == '-rev':
                    svgeditor2taskcode_kwargs['is_reverse_engraving'] = True
                elif param == '-mask':
                    clip_rect = [0, 0, 0, 0] # top right bottom left
                    try:
                        clip_rect = [float(j) for j in params[i+1].split(',')]
                    except Exception:
                        pass
                    svgeditor2taskcode_kwargs['clip'] = clip_rect
                elif param == '-cbl':
                    svgeditor2taskcode_kwargs['custom_backlash'] = True
                elif param == '-mep':
                    try:
                        svgeditor2taskcode_kwargs['min_engraving_padding'] = int(params[i+1])
                    except Exception:
                        pass
                elif param == '-mpp':
                    try:
                        svgeditor2taskcode_kwargs['min_printing_padding'] = int(params[i+1])
                    except Exception:
                        pass
                elif param == '-mpc':
                    svgeditor2taskcode_kwargs['multipass_compensation'] = True
                elif param == '-owp':
                    svgeditor2taskcode_kwargs['one_way_printing'] = True
                elif param == '-ptp':
                    try:
                        svgeditor2taskcode_kwargs['printing_top_padding'] = int(params[i+1])
                    except Exception:
                        pass
                elif param == '-pbp':
                    try:
                        svgeditor2taskcode_kwargs['printing_bot_padding'] = int(params[i+1])
                    except Exception:
                        pass
                elif param == '-nv':
                    try:
                        svgeditor2taskcode_kwargs['nozzle_votage'] = float(params[i+1])
                    except Exception:
                        pass
                elif param == '-npw':
                    try:
                        svgeditor2taskcode_kwargs['nozzle_pulse_width'] = float(params[i+1])
                    except Exception:
                        pass
                elif param == '-mof':
                    # module offset
                    value = json.loads(params[i+1])
                    svgeditor2taskcode_kwargs['module_offsets'] = value
                elif param == '-ts':
                    try:
                        svgeditor2taskcode_kwargs['travel_speed'] = int(params[i+1])
                    except Exception:
                        pass
                elif param == '-pts':
                    try:
                        svgeditor2taskcode_kwargs['path_travel_speed'] = int(params[i+1])
                    except Exception:
                        pass
                elif param == '-ats':
                    try:
                        svgeditor2taskcode_kwargs['a_travel_speed'] = int(params[i+1])
                    except Exception:
                        pass
                elif param == '-no-pwm':
                    svgeditor2taskcode_kwargs['no_pwm'] = True
                elif param == '-job-origin':
                    try:
                        origin = params[i + 1].split(',')
                        x = float(origin[0])
                        y = float(origin[1])
                        svgeditor2taskcode_kwargs['job_origin'] = [x, y]
                        start_with_home = False
                    except Exception:
                        logger.exception('Invalid job origin')
                        pass

            self.factory_kwargs['hardware_name'] = hardware_name
            svgeditor2taskcode_kwargs['hardware_name'] = hardware_name

            try:
                self.send_progress('Initializing', 0.03)
                factory = self.prepare_factory()
                self.fcode_metadata.update({
                    'CREATED_AT': datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ'),
                    'AUTHOR': urllib.parse.quote(get_username()),
                    'SOFTWARE': 'fluxclient-%s-BS' % __version__,
                    'START_WITH_HOME': '1' if start_with_home else '0',
                })
                logger.info('FCode Version: %d', fcode_version)
                time_need = 0
                traveled_dist = 0
                metadata = {}
                if output_fcode:
                    thumbnail = factory.generate_thumbnail()
                    if fcode_version == 2:
                        magic_number = 4 if (is_rotary_task or not start_with_home) else 3
                        writer = FCodeV2MemoryWriter(self.fcode_metadata, (thumbnail, ), magic_number)
                    else:
                        writer = FCodeV1MemoryWriter('LASER', self.fcode_metadata, (thumbnail, ))
                else:
                    writer = GCodeMemoryWriter()

                svgeditor2taskcode(writer, factory,
                                progress_callback=progress_callback,
                                check_interrupted=self.check_interrupted,
                                **svgeditor2taskcode_kwargs)
                if output_fcode:
                    time_need = writer.get_time_cost()
                    traveled_dist = writer.get_traveled()
                writer.terminated()
                if output_fcode:
                    try:
                        metadata = writer.get_metadata()
                        metadata = {key.decode('utf-8'): value.decode('utf-8') for key, value in metadata.items()}
                    except Exception:
                        logger.exception('Failed to get metadata')
                        metadata = ''

                if self.check_interrupted():
                    logger.info('cmd go interrupted')
                    return

                output_binary = writer.get_buffer()
                print('time cost:', time_need, '\ntravel distance', traveled_dist)
                self.send_progress('Finishing', 1.0)
                if send_fcode:
                    self.send_json(status="complete", length=len(output_binary), time=time_need, traveled_dist=traveled_dist, metadata=metadata)
                    self.send_binary(output_binary)
                else:
                    output_file = open("/var/gcode/userspace/temp.fc", "wb")
                    output_file.write(output_binary)
                    output_file.close()
                    self.send_json(status="complete", file="/var/gcode/userspace/temp.fc")
                logger.info("Svg Editor Processed")
            except Exception as e:
                traceback_info = traceback.extract_tb(e.__traceback__)
                file_name, line_number, _, _ = traceback_info[-1]
                self.send_json(status='Error', message='{}\n{}, line: {}'.format(str(e), file_name, line_number))
                raise e

        def cmd_interrupt(self, params):
            self.is_task_interrupted = True
            self.send_ok()

        def check_interrupted(self) :
            return self.is_task_interrupted

        def _handle_message(self, opcode, message):
            msg_thread = threading.Thread(
                target=super()._handle_message,
                args=[opcode, message]
            )
            msg_thread.start()

    return LaserSvgeditorApi
