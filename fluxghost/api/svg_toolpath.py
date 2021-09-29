
from datetime import datetime
import logging

from fluxclient.toolpath.svg_factory import SvgImage, SvgFactory
from fluxclient.toolpath.penholder import svg2drawing, svg2vinyl
from fluxclient.toolpath.laser import svg2laser, svgeditor2laser
from fluxclient.toolpath import FCodeV1MemoryWriter, GCodeMemoryWriter
from fluxclient import __version__

from fluxghost.utils.username import get_username
from .misc import BinaryUploadHelper, BinaryHelperMixin, OnTextMessageMixin

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


def laser_svg_api_mixin(cls):
    class LaserSvgApi(OnTextMessageMixin, svg_base_api_mixin(cls)):
        max_engraving_strength = 1.0

        def __init__(self, *args):
            super().__init__(*args)
            self.svgs = {}
            self.cmd_mapping = {
                'upload': [self.cmd_upload_svg],
                'compute': [self.cmd_upload_svg_and_preview],
                'get': [self.cmd_get],
                'go': [self.cmd_process],
                'set_params': [self.cmd_set_params],
                'meta_option': [self.cmd_set_fcode_metadata]
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

            self.send_progress('Initializing', 0.03)
            factory = self.prepare_factory(names)

            self.fcode_metadata.update({
                "CREATED_AT": datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
                "AUTHOR": get_username(),
                "SOFTWARE": "fluxclient-%s-FS" % __version__,
            })
            self.fcode_metadata["OBJECT_HEIGHT"] = str(self.object_height)
            self.fcode_metadata["HEIGHT_OFFSET"] = str(self.height_offset)
            self.fcode_metadata["BACKLASH"] = "Y"

            if output_fcode:
                preview = factory.generate_preview()
                writer = FCodeV1MemoryWriter("LASER", self.fcode_metadata,
                                             (preview, ))
            else:
                writer = GCodeMemoryWriter()

            def progress_callback(prog):
                pass

            svg2laser(writer, factory,
                      z_height=self.object_height + self.height_offset,
                      travel_speed=2400, engraving_speed=self.working_speed,
                      engraving_strength=self.max_engraving_strength,
                      progress_callback=progress_callback)
            writer.terminated()
            output_binary = writer.get_buffer()
            time_need = float(writer.get_metadata().get(b"TIME_COST", 0)) \
                if output_fcode else 0

            self.send_progress('finishing', 1.0)
            self.send_json(status="complete", length=len(output_binary),
                           time=time_need)
            self.send_binary(output_binary)
            logger.info("Laser svg processed")

    return LaserSvgApi

def drawing_svg_api_mixin(cls):
    class DrawingSvgApi(OnTextMessageMixin, svg_base_api_mixin(cls)):
        def __init__(self, *args):
            super().__init__(*args)
            self.cmd_mapping = {
                'upload': [self.cmd_upload_svg],
                'compute': [self.cmd_upload_svg_and_preview],
                'get': [self.cmd_get],
                'go': [self.cmd_process],
                'set_params': [self.cmd_set_params],
                'meta_option': [self.cmd_set_fcode_metadata]
            }

        def cmd_set_params(self, params):
            logger.info('set params %r', params)
            key, value = params.split()
            if not self.set_param(key, value):
                if key == 'speed':
                    # TODO rename
                    self.working_speed = float(value) * 60
                elif key == 'draw_height':
                    self.object_height = float(value)
                elif key == 'lift_height':
                    # TODO rename
                    self.travel_lift = float(value)
                else:
                    raise KeyError('Bad key: %r' % key)
            self.send_ok()

        def cmd_process(self, params):
            names = params.split(" ")
            logger.info('Process drawing svg')

            self.send_progress('Initializing', 0.03)
            factory = self.prepare_factory(names)

            preview = factory.generate_preview()

            self.fcode_metadata.update({
                "CREATED_AT": datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
                "AUTHOR": get_username(),
                "SOFTWARE": "fluxclient-%s-FS" % __version__,
            })
            self.fcode_metadata["OBJECT_HEIGHT"] = str(self.object_height)
            self.fcode_metadata["HEIGHT_OFFSET"] = str(self.height_offset)
            self.fcode_metadata["BACKLASH"] = "Y"
            writer = FCodeV1MemoryWriter("N/A", self.fcode_metadata,
                                         (preview, ))

            def progress_callback(prog):
                pass

            object_h = self.object_height + self.height_offset
            travel_h = object_h + self.travel_lift
            svg2drawing(writer, factory,
                        drawing_zheight=object_h,
                        travel_zheight=travel_h,
                        drawing_speed=self.working_speed,
                        travel_speed=self.travel_speed,
                        progress_callback=progress_callback)
            writer.terminated()
            output_binary = writer.get_buffer()
            meta = writer.get_metadata()
            time_need = float(meta.get(b'TIME_COST', '0.01'))
            self.send_progress('finishing', 1.0)
            self.send_json(status="complete", length=len(output_binary),
                           time=time_need)
            self.send_binary(output_binary)
            logger.info("Processed drawing SVG")
    return DrawingSvgApi


def vinyl_svg_api_mixin(cls):
    class VinylSvgApi(OnTextMessageMixin, svg_base_api_mixin(cls)):
        precut_at = None
        blade_radius = 0.28
        overcut = 2
        repeat = 1
        step_height = 0.1
        height_offset = -0.4

        def __init__(self, *args):
            super().__init__(*args)
            self.cmd_mapping = {
                'upload': [self.cmd_upload_svg],
                'compute': [self.cmd_upload_svg_and_preview],
                'get': [self.cmd_get],
                'go': [self.cmd_process],
                'set_params': [self.cmd_set_params],
                'meta_option': [self.cmd_set_fcode_metadata]
            }

        def cmd_set_params(self, params):
            logger.info('Set params %r', params)
            key, svalue = params.split()
            if not self.set_param(key, svalue):
                if key == 'cutting_speed':
                    value = float(svalue) * 60  # mm/s -> mm/min
                    assert value > 0
                    self.working_speed = value
                elif key == 'travel_speed':
                    value = float(svalue) * 60  # mm/s -> mm/min
                    assert value > 0
                    self.travel_speed = value
                elif key == 'cutting_zheight':
                    value = float(svalue)
                    self.object_height = value
                elif key == 'precut':
                    sx, sy = svalue.split(",")
                    self.precut_at = (float(sx), float(sy))
                elif key == 'blade_radius':
                    value = float(svalue)
                    self.blade_radius = value
                elif key == 'overcut':
                    value = float(svalue)
                    self.overcut = value
                elif key == 'repeat':
                    value = int(svalue)
                    self.repeat = value
                elif key == 'step_height':
                    value = float(svalue)
                    self.step_height = value
                elif key == 'speed':
                    # TODO rename
                    self.working_speed = float(svalue) * 60
                elif key == 'draw_height':
                    # TODO rename
                    self.object_height = float(svalue)
                elif key == 'lift_height':
                    # TODO rename
                    self.travel_lift = float(svalue)
                else:
                    raise KeyError('Bad key: %r' % key)
            self.send_ok()

        def cmd_process(self, params):
            names = params.split(" ")
            logger.info('Process vinyl svg')

            self.send_progress('Initializing', 0.03)
            factory = self.prepare_factory(names)

            preview = factory.generate_preview()

            self.fcode_metadata.update({
                "CREATED_AT": datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
                "AUTHOR": get_username(),
                "SOFTWARE": "fluxclient-%s-FS" % __version__,
            })
            self.fcode_metadata["OBJECT_HEIGHT"] = str(self.object_height)
            self.fcode_metadata["HEIGHT_OFFSET"] = str(self.height_offset)
            self.fcode_metadata["BACKLASH"] = "Y"
            self.fcode_metadata["TASK_TYPE"] = "VINYL"
            writer = FCodeV1MemoryWriter("N/A", self.fcode_metadata,
                                         (preview, ))

            def progress_callback(prog):
                pass

            object_h = self.object_height + self.height_offset
            travel_h = object_h + self.travel_lift

            for i in range(self.repeat):
                svg2vinyl(writer, factory,
                          travel_speed=self.travel_speed,
                          cutting_speed=self.working_speed,
                          travel_zheight=travel_h - i * self.step_height,
                          cutting_zheight=object_h - i * self.step_height,
                          blade_radius=self.blade_radius,
                          overcut=self.overcut,
                          precut_at=self.precut_at,
                          progress_callback=progress_callback)

            if self.repeat > 1:
                writer.moveto(feedrate=5000, x=0, y=0, z=150)
                for i in range(600):
                    writer.sleep(1)

            writer.terminated()
            output_binary = writer.get_buffer()
            meta = writer.get_metadata()
            time_need = float(meta.get(b'TIME_COST', '0.01'))
            self.send_progress('finishing', 1.0)
            self.send_json(status="complete", length=len(output_binary),
                           time=time_need)
            self.send_binary(output_binary)
            logger.info("Processed Vinyl SVG")
    return VinylSvgApi
