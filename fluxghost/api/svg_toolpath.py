
import logging

from fluxclient.toolpath.svg_factory import SvgImage, SvgFactory
from fluxclient.toolpath.laser import svg2laser
from fluxclient.toolpath import FCodeV1MemoryWriter, GCodeMemoryWriter
from .misc import BinaryUploadHelper, BinaryHelperMixin, OnTextMessageMixin

logger = logging.getLogger("API.SVG")


def svg_base_api_mixin(cls):
    class SvgBaseApi(BinaryHelperMixin, cls):
        fcode_metadata = None
        svgs = None

        def cmd_set_fcode_metadata(self, params):
            key, value = params.split()
            logger.info('meta_option {}'.format(key))
            self.fcode_metadata[key] = value
            self.send_ok()

    return SvgBaseApi


def laser_svg_api_mixin(cls):
    class LaserSvgApi(OnTextMessageMixin, svg_base_api_mixin(cls)):
        object_height = 0.0
        height_offset = 0.0
        engraving_speed = 0
        max_engraving_strength = 1.0

        def __init__(self, *args):
            super().__init__(*args)
            self.fcode_metadata = {}
            self.svgs = {}
            self.cmd_mapping = {
                'upload': [self.cmd_upload_svg],
                'compute': [self.cmd_upload_svg_and_preview],
                'get': [self.cmd_fetch_svg],
                'go': [self.cmd_process],
                'set_params': [self.cmd_set_params],
                'meta_option': [self.cmd_set_fcode_metadata]
            }

        def cmd_upload_svg(self, message):
            def upload_callback(buf, name):
                svg_image = SvgImage(buf)
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
                    svg_image.set_svg(buf[:-preview_bitmap_size])
                    svg_image.set_preview(preview_size,
                                          buf[-preview_bitmap_size:])
                    svg_image.set_image_coordinate(point1, point2, rotation)
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

        def cmd_set_params(self, params):
            logger.info('set params %r', params)
            key, value = params.split()
            if key == 'object_height':
                self.object_height = float(value)
            elif key == 'height_offset':
                self.height_offset = float(value)
            elif key == 'laser_speed':
                self.engraving_speed = float(value) * 60  # mm/s -> mm/min
            elif key == 'power':
                self.max_engraving_strength = min(1, float(value))
            elif key in ('shading', 'one_way', 'focus_by_color'):
                pass
            else:
                raise KeyError('Bad key: %r' % key)
            self.send_ok()

        def cmd_process(self, params):
            logger.info('Process laser svg')
            names = params.split()
            output_fcode = True
            if names[-1] == '-f':
                names = names[:-1]
                output_fcode = True
            elif names[-1] == '-g':
                names = names[:-1]
                output_fcode = False

            factory = SvgFactory()
            self.send_progress('Initializing', 0.03)

            for name in names:
                svg_image = self.svgs.get(name, None)
                if svg_image is None:
                    logger.error("Can not find svg named %r", name)
                    continue
                factory.add_image(svg_image)

            if output_fcode:
                preview = factory.generate_preview()
                self.fcode_metadata["OBJECT_HEIGHT"] = str(self.object_height)
                self.fcode_metadata["HEIGHT_OFFSET"] = str(self.height_offset)
                # self.fcode_metadata["BACKLASH"] = "Y"
                writer = FCodeV1MemoryWriter("LASER", self.fcode_metadata,
                                             (preview, ))
            else:
                writer = GCodeMemoryWriter()

            def progress_callback(prog):
                pass

            svg2laser(writer, factory,
                      z_height=self.object_height + self.height_offset,
                      travel_speed=2400, engraving_speed=self.engraving_speed,
                      engraving_strength=self.max_engraving_strength,
                      progress_callback=progress_callback)
            writer.terminated()
            output_binary = writer.get_buffer()
            time_need = float(writer.get_metadata().get("TIME_COST", 0)) \
                if output_fcode else 0

            self.send_progress('finishing', 1.0)
            self.send_json(status="complete", length=len(output_binary),
                           time=time_need)
            self.send_binary(output_binary)
            logger.info("Laser svg processed")

    return LaserSvgApi
