from datetime import datetime
from getpass import getuser
import logging

from fluxclient.toolpath.svgeditor_factory import SvgeditorImage, SvgeditorFactory
from fluxclient.toolpath.laser import svgeditor2laser
from fluxclient.toolpath import FCodeV1MemoryWriter, GCodeMemoryWriter
from fluxclient import __version__

import fluxsvg

from .misc import BinaryUploadHelper, BinaryHelperMixin, OnTextMessageMixin

logger = logging.getLogger("API.SVGEDITOR")

def svg_base_api_mixin(cls):
    class SvgBaseApi(BinaryHelperMixin, cls):
        fcode_metadata = None
        object_height = 0.0
        height_offset = 0.0
        working_speed = 1200
        travel_speed = 2400
        travel_lift = 5.0
        svgs = None

        def __init__(self, *args, **kw):
            super(SvgBaseApi, self).__init__(*args, **kw)
            self.svgs = {}
            self.fcode_metadata = {}

        def set_param(self, key, value):
            if key == 'object_height':
                self.object_height = float(value)
            elif key == 'height_offset':
                self.height_offset = float(value)
            elif key == 'travel_lift':
                fvalue = float(value)
                assert fvalue > 0
                self.travel_lift = fvalue
            else:
                return False
            return True

        def prepare_factory(self, names):
            factory = SvgeditorFactory()
            self.send_progress('Initializing', 0.03)

            for i, name in enumerate(names):
                svg_image = self.svgs.get(name, None)
                if svg_image is None:
                    logger.error("Can not find svg named %r", name)
                    continue
                logger.info("Preprocessing image %s", name)
                self.send_progress('Processing image',
                                   (i / len(names) * 0.3 + 0.10))

                factory.add_image(svg_image)
            return factory

        def cmd_upload_svg(self, message):
            def upload_callback(buf, name):
                try:
                    svg_image = SvgImage(buf)
                except Exception:
                    logger.exception("Load SVG Error")
                    self.send_error("SVG_BROKEN")
                    return
                for error in svg_image.errors:
                    self.send_warning(error)
                self.svgs[name] = svg_image
                self.send_ok()

            name, file_length = message.split()
            helper = BinaryUploadHelper(
                int(file_length), upload_callback, name)
            self.set_binary_helper(helper)
            self.send_json(status="continue")

        def cmd_upload_svg_and_preview(self, params):
            def upload_callback(buf, name, preview_size, point1, point2,
                                rotation, preview_bitmap_size):
                svg_image = self.svgs.get(name, None)
                if svg_image:
                    pass
                    #svg_image.set_svg(buf[:-preview_bitmap_size])
                    #svg_image.set_preview(preview_size,
                    #                      buf[-preview_bitmap_size:])
                    #svg_image.set_image_coordinate(point1, point2, rotation)
                else:
                    logger.error("Can not find SVG name %r", name)
                self.send_ok()

            logger.info('compute')

            options = params.split()
            name = options[0]
            # w, h = float(options[1]), float(options[2])
            x1, y1, x2, y2 = (float(o) for o in options[3:7])
            rotation = float(options[7])
            svg_length = int(options[8])
            bitmap_w = int(options[9])
            bitmap_h = int(options[10])

            helper = BinaryUploadHelper(
                svg_length + bitmap_w * bitmap_h, upload_callback, name,
                (bitmap_w, bitmap_h), (x1, y1), (x2, y2), rotation,
                bitmap_w * bitmap_h)
            self.set_binary_helper(helper)
            self.send_json(status="continue")

        def cmd_fetch_svg(self, name):
            svg_image = self.svgs.get(name, None)
            if svg_image:
                self.send_json(
                    status="continue", length=len(svg_image.buf),
                    width=svg_image.viewbox_width,
                    height=svg_image.viewbox_height)
                self.send_binary(svg_image.buf)
            else:
                logger.error("%r svg not found", name)
                self.send_error('NOT_FOUND')

        def cmd_set_fcode_metadata(self, params):
            key, value = params.split()
            logger.info('meta_option {}'.format(key))
            self.fcode_metadata[key] = value
            self.send_ok()

    return SvgBaseApi

def laser_svgeditor_api_mixin(cls):
    class LaserSvgeditorApi(OnTextMessageMixin, svg_base_api_mixin(cls)):
        def __init__(self, *args):
            self.max_engraving_strength = 1.0
            self.pixel_per_mm = 20
            super().__init__(*args)
            self.cmd_mapping = {
                'upload_plain_svg': [self.cmd_upload_plain_svg],
                'divide_svg': [self.divide_svg],
                'svgeditor_upload': [self.cmd_upload_svg_and_thumbnail],
                'go': [self.cmd_process],
                'set_params': [self.cmd_set_params],
            }

        def cmd_set_params(self, params):
            logger.info('set params %r', params)
            key, value = params.split()
            if not self.set_param(key, value):
                if key == 'laser_speed':
                    self.working_speed = float(value) * 60  # mm/s -> mm/min
                elif key == 'power':
                    self.max_engraving_strength = min(1, float(value))
                elif key in ('shading', 'one_way', 'calibration'):
                    pass
                else:
                    raise KeyError('Bad key: %r' % key)
            self.send_ok()

        def divide_svg(self, params):
            outputs = fluxsvg.divide(self.plain_svg)
            self.send_json(name="strokes", length=outputs[0].getbuffer().nbytes)
            self.send_binary(outputs[0].getbuffer())
            self.send_json(name="bitmap", length=outputs[1].getbuffer().nbytes)
            self.send_binary(outputs[1].getbuffer())
            self.send_json(name="colors", length=outputs[2].getbuffer().nbytes)
            self.send_binary(outputs[2].getbuffer())
            self.send_ok()

        def cmd_upload_svg_and_thumbnail(self, params):
            def gen_svgs_database(buf, name, thumbnail_length):
                try:
                    thumbnail = buf[:thumbnail_length]
                    svg_data = buf[thumbnail_length:]
                    svgeditor_image = SvgeditorImage(
                                thumbnail, svg_data, self.pixel_per_mm)
                except Exception:
                    logger.exception("Load SVG Error")
                    self.send_error("SVG_BROKEN")
                    return
                self.svg = svgeditor_image

            def upload_callback(buf, name, thumbnail_length):
                gen_svgs_database(buf, name, thumbnail_length)
                self.send_ok()

            logger.info('svg_editor')

            name, file_length, thumbnail_length = params.split()
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

        def prepare_factory(self):
            factory = SvgeditorFactory(self.pixel_per_mm)
            factory.add_image(self.svg.groups, self.svg.params)
            factory.add_thumbnail(self.svg.thumbnail)
            return factory

        def cmd_process(self, params):
            def progress_callback(title, prog):
                self.send_progress(title, prog)

            logger.info('Process laser svgeditor')
            #names = params.split()
            output_fcode = True
            #if names[-1] == '-f':
            #    names = names[:-1]
            #    output_fcode = True
            #elif names[-1] == '-g':
            #    names = names[:-1]
            #    output_fcode = False

            self.send_progress('Initializing', 0.03)
            factory = self.prepare_factory()

            self.fcode_metadata.update({
                "CREATED_AT": datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
                "AUTHOR": getuser(),
                "SOFTWARE": "fluxclient-%s-FS" % __version__,
            })
            self.fcode_metadata["OBJECT_HEIGHT"] = str(self.object_height)
            self.fcode_metadata["HEIGHT_OFFSET"] = str(self.height_offset)
            self.fcode_metadata["BACKLASH"] = "Y"

            if output_fcode:
                thumbnail = factory.generate_thumbnail()
                writer = FCodeV1MemoryWriter("LASER", self.fcode_metadata,
                                             (thumbnail, ))
            else:
                writer = GCodeMemoryWriter()

            svgeditor2laser(
                        writer, factory,
                        z_height=self.object_height + self.height_offset,
                        travel_speed=12000,
                        engraving_strength=self.max_engraving_strength,
                        progress_callback=progress_callback
                    )
            writer.terminated()

            output_binary = writer.get_buffer()
            time_need = float(writer.get_metadata().get(b"TIME_COST", 0)) \
                if output_fcode else 0

            self.send_progress('finishing', 1.0)
            self.send_json(status="complete", length=len(output_binary),
                           time=time_need)
            self.send_binary(output_binary)
            logger.info("Laser svg processed")

    return LaserSvgeditorApi
