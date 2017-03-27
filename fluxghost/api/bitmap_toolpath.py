
from time import time
import logging

from fluxclient.toolpath.bitmap_factory import BitmapImage, BitmapFactory
from fluxclient.toolpath.laser import bitmap2laser
from fluxclient.toolpath import FCodeV1MemoryWriter, GCodeMemoryWriter
from .misc import BinaryUploadHelper, BinaryHelperMixin, OnTextMessageMixin

logger = logging.getLogger("API.BITMAP")


def bitmap_base_api_mixin(cls):
    class BitmapBaseApi(BinaryHelperMixin, cls):
        fcode_metadata = None
        images = None
        shading = True

        def begin_upload_image(self, length, x1, y1, x2, y2, width, height,
                               rotation, thres):
            def complete(buf, size, point1, point2, rotation, thres):
                self.images.append(
                    BitmapImage(buf, size, point1, point2, rotation, thres)
                )
                self.send_json(status="accept")
                logger.info("Image uploaded (size: %s, position: %s, %s, "
                            "rotation: %s, thres: %s)", size, point1, point2,
                            rotation, thres)

            helper = BinaryUploadHelper(
                length, complete, (width, height), (x1, y1), (x2, y2),
                rotation, thres)
            self.set_binary_helper(helper)
            self.send_json(status="continue")

        def cmd_set_fcode_metadata(self, params):
            key, value = params.split()
            logger.info('Set fcode metadata {}'.format(key))
            self.fcode_metadata[key] = value
            self.send_ok()

    return BitmapBaseApi


def laser_bitmap_api_mixin(cls):
    class LaserBitmapApi(OnTextMessageMixin, bitmap_base_api_mixin(cls)):
        one_way = True
        object_height = 0.0
        height_offset = 0.0
        engraving_speed = 0
        max_engraving_strength = 1.0

        def __init__(self, *args):
            super().__init__(*args)
            self.cmd_reset()
            self.cmd_mapping = {
                'upload': [self.cmd_upload_bitmap],
                'go': [self.cmd_process],
                'set_params': [self.cmd_set_params],
                'clear_imgs': [self.cmd_reset],
                'meta_option': [self.cmd_set_fcode_metadata]
            }

        def cmd_upload_bitmap(self, message):
            options = message.split()
            print(options)
            w, h = int(options[0]), int(options[1])
            x1, y1, x2, y2 = (float(o) for o in options[2:6])
            rotation = float(options[6])
            thres = int(options[7])
            image_size = w * h
            self.begin_upload_image(image_size, x1, y1, x2, y2, w, h,
                                    rotation, thres)

        def cmd_reset(self, *args):
            logger.info('Reset')
            self.fcode_metadata = {}
            self.images = []
            self.send_ok()

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
            elif key == 'shading':
                self.shading = int(value) == 1
            elif key == 'one_way':
                self.one_way = int(value) == 1
            else:
                raise KeyError('Bad key: %r' % key)
            self.send_ok()

        def cmd_process(self, *args):
            logger.info('Process laser bitmap')
            self.send_progress('Initializing', 0.03)

            factory = BitmapFactory()
            self.send_progress('Initializing', 0.10)

            for i, bitmap_image in enumerate(self.images, start=1):
                logger.info("Preprocessing image %s", bitmap_image)
                self.send_progress('Processing image',
                                   (i / len(self.images) * 0.3 + 0.10))
                factory.add_image(bitmap_image)

            if '-g' in args:
                writer = GCodeMemoryWriter()
            else:
                preview = factory.generate_preview()
                self.fcode_metadata["OBJECT_HEIGHT"] = str(self.object_height)
                self.fcode_metadata["HEIGHT_OFFSET"] = str(self.height_offset)
                writer = FCodeV1MemoryWriter("LASER", self.fcode_metadata,
                                             (preview, ))

            def bitmap2laser_progress(prog):
                if time() - self.last_report > 0.15:
                    self.send_progress('Generating FCode', prog * 0.59 + 0.40)
                    self.last_report = time()
            self.last_report = 0

            logger.info("Processing toolpath")
            bitmap2laser(writer, factory,
                         z_height=self.object_height + self.height_offset,
                         one_way=self.one_way, vertical=False,
                         shading=self.shading,
                         engraving_speed=self.engraving_speed,
                         max_engraving_strength=self.max_engraving_strength,
                         progress_callback=bitmap2laser_progress)

            writer.terminated()
            output_binary = writer.get_buffer()
            time_need = 0 if '-g' in args else \
                float(writer.get_metadata().get(b"TIME_COST", 0))

            self.send_progress('finishing', 1.0)
            self.send_json(status="complete", length=len(output_binary),
                           time=time_need)
            self.send_binary(output_binary)
            logger.info("Laser bitmap processed")
    return LaserBitmapApi
