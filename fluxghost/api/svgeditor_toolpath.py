import math
import re
from datetime import datetime
from getpass import getuser
import logging

from fluxclient.toolpath.svgeditor_factory import SvgeditorImage, SvgeditorFactory

from fluxclient.toolpath.laser import svgeditor2laser
from fluxclient.toolpath import FCodeV1MemoryWriter, GCodeMemoryWriter
from fluxclient import __version__

import fluxsvg

from .svg_toolpath import svg_base_api_mixin
from .misc import BinaryUploadHelper, BinaryHelperMixin, OnTextMessageMixin

logger = logging.getLogger("API.SVGEDITOR")

def laser_svgeditor_api_mixin(cls):
    class LaserSvgeditorApi(OnTextMessageMixin, svg_base_api_mixin(cls)):
        def __init__(self, *args):
            self.max_engraving_strength = 1.0
            self.pixel_per_mm = 10
            self.svg_image = None
            self.hardware_name = "beambox"
            self.loop_compensation = 0.0
            super().__init__(*args)
            self.cmd_mapping = {
                'upload_plain_svg': [self.cmd_upload_plain_svg],
                'divide_svg': [self.divide_svg],
                'svgeditor_upload': [self.cmd_svgeditor_upload],
                'go': [self.cmd_go],
                'set_params': [self.cmd_set_params],
            }

        def cmd_set_params(self, params):
            key, value = params.split()
            logger.info('setting parameter %r  = %r', key, value)
            if not self.set_param(key, value):
                if key == 'laser_speed':
                    self.working_speed = float(value) * 60  # mm/s -> mm/min
                elif key == 'power':
                    self.max_engraving_strength = min(1, float(value))
                elif key == 'loop_compensation':
                    self.loop_compensation = max(0, float(value))
                elif key in ('shading', 'one_way', 'calibration'):
                    pass
                else:
                    raise KeyError('Bad key: %r' % key)
            self.send_ok()

        def divide_svg(self, params):
            
            self.plain_svg = self.plain_svg.replace(b'encoding="UTF-16"', b'encoding="utf-8"')
            self.plain_svg = self.plain_svg.replace(b'encoding="utf-16"', b'encoding="utf-8"')
            result = fluxsvg.divide(self.plain_svg, loop_compensation=self.loop_compensation)

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

        def cmd_svgeditor_upload(self, params):

            def progress_callback(prog):
                self.send_progress("Analyzing SVG - " + str(round(prog * 100, 2)) + "%", prog)

            def generate_svgeditor_image(buf, name, thumbnail_length):
                try:
                    thumbnail = buf[:thumbnail_length]
                    svg_data = buf[thumbnail_length:]
                    svg_image = SvgeditorImage(thumbnail, svg_data, self.pixel_per_mm, 
                                                hardware=self.hardware_name,
                                                loop_compensation=self.loop_compensation,
                                                progress_callback=progress_callback,
                                                enable_mask=self.enable_mask)
                except Exception as e:
                    logger.exception("Load SVG Error")
                    logger.exception(str(e))
                    self.send_error("SVG_BROKEN")
                    return
                self.svg_image = svg_image

            def upload_callback(buf, name, thumbnail_length):
                generate_svgeditor_image(buf, name, thumbnail_length)
                self.send_ok()

            logger.info('svg_editor')
            params = params.split()
            name = params[0]
            file_length = params[1]
            thumbnail_length = params[2]
            self.hardware_name = 'beambox'
            if '-pro' in params:
                max_x = 600 
                self.hardware_name = 'beambox-pro'

            if '-beamo' in params:
                max_x = 300 
                self.hardware_name = 'beamo'

            if '-ldpi' in params:
                self.pixel_per_mm = 5
            
            if '-mdpi' in params:
                self.pixel_per_mm = 10
            
            if '-hdpi' in params:
                self.pixel_per_mm = 20
            self.enable_mask = False
            if '-mask' in params:
                self.enable_mask = True

            file_length, thumbnail_length = map(int, (file_length, thumbnail_length))
            helper = BinaryUploadHelper(
                    file_length, upload_callback, name, thumbnail_length)

            self.set_binary_helper(helper)
            self.send_json(status="continue")
        
        def cmd_upload_plain_svg(self, params):
            def upload_callback(buf, name):
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

        def prepare_factory(self, hardware_name):
            factory = SvgeditorFactory(self.pixel_per_mm, hardware_name=hardware_name, loop_compensation=self.loop_compensation)
            factory.add_image(self.svg_image)
            return factory

        def cmd_go(self, params_str):
            def progress_callback(prog):
                prog = math.floor(prog * 500) / 500
                self.send_progress("Calculating Toolpath " + str(round(prog * 100, 2)) + "%", prog)

            logger.info('Calling laser svgeditor')
            output_fcode = True
            params = params_str.split()
            default_travel_speed = 7500
            max_x = 400
            hardware_name = 'beambox'
            spinning_axis_coord = -1
            send_fcode = True

            if '-pro' in params:
                max_x = 600 
                hardware_name = 'beambox-pro'
            
            if '-beamo' in params:
                max_x = 300 
                hardware_name = 'beamo'
            
            if '-film' in params:
                self.fcode_metadata["CONTAIN_PHONE_FILM"] = '1'

            if '-spin' in params:
                travel_speed = 4000
                spinning_axis_coord = float(params[params.index('-spin')+1])
            
            if '-temp' in params:
                send_fcode = False

            self.send_progress('Initializing', 0.03)
            factory = self.prepare_factory(hardware_name)

            self.fcode_metadata.update({
                "CREATED_AT": datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
                "AUTHOR": getuser(),
                "SOFTWARE": "fluxclient-%s-FS" % __version__,
            })
            
            if output_fcode:
                thumbnail = factory.generate_thumbnail()
                writer = FCodeV1MemoryWriter("LASER", self.fcode_metadata,
                                             (thumbnail, ))
            else:
                writer = GCodeMemoryWriter()

            svgeditor2laser(writer, factory, z_height=self.object_height + self.height_offset,
                        travel_speed=default_travel_speed,
                        engraving_strength=self.max_engraving_strength,
                        progress_callback=progress_callback,
                        max_x=max_x,
                        spinning_axis_coord=spinning_axis_coord)
            
            writer.terminated()

            output_binary = writer.get_buffer()
            time_need = float(writer.get_metadata().get(b"TIME_COST", 0)) \
                if output_fcode else 0
            
            traveled_dist = float(writer.get_metadata().get(b"TRAVEL_DIST", 0)) \
                if output_fcode else 0

            self.send_progress('Finishing', 1.0)
            if send_fcode:
                self.send_json(status="complete", length=len(output_binary), time=time_need, traveled_dist=traveled_dist)
                self.send_binary(output_binary)
            else:
                output_file = open("/var/gcode/userspace/temp.fc", "wb")
                output_file.write(output_binary)
                output_file.close()
                self.send_json(status="complete", file="/var/gcode/userspace/temp.fc")
            logger.info("Svg Editor Processed")

    return LaserSvgeditorApi
