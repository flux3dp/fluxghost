
import logging

from fluxclient.toolpath.svg_factory import SvgImage, SvgFactory
from fluxclient.toolpath import FCodeV1MemoryWriter, GCodeMemoryWriter
from fluxclient import __version__

from fluxghost.utils.username import get_username
from .misc import BinaryUploadHelper, BinaryHelperMixin

logger = logging.getLogger("API.SVG")


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
            factory = SvgFactory()
            self.send_progress('Initializing', 0.03)

            print('self.svgs', self.svgs)
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

        def cmd_get(self, name):
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
