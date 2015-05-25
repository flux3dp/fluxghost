# !/usr/bin/env python3
from math import pi, sin, cos


class laser_pattern():
    """laser_pattern"""
    def __init__(self):
        laser_on = False  # recording if laser is on
        pixel_per_mm = 2  # how many pixel is 1 mm
        radius = 75  # laser max radius = 75
        focal_l = 11 + 3 - 0.7  # focal z coordinate
        self.thres = 100
        rotation = 0
        ratio = 1.
        image_map = [[255 for _ in range(pixel_per_mm * radius * 2)] for _ in range(pixel_per_mm * radius * 2)]  # main image

    def moveTo(self, x, y):
        x = float(x) / pixel_per_mm - self.radius
        y = float(len(self.image_map) - y) / pixel_per_mm - self.radius

        x2 = x * cos(rotation) + y * sin(rotation)
        y2 = x * -sin(rotation) + y * cos(rotation)

        x = x2 / ratio
        y = y2 / ratio
        return ["G1 F600 X" + str(x) + " Y" + str(y)]

    def drawTo(self, x, y, speed=None):
        x = float(x) / pixel_per_mm - self.radius
        y = float(len(self.image_map) - y) / pixel_per_mm - self.radius

        x2 = x * cos(rotation) + y * sin(rotation)
        y2 = x * -sin(rotation) + y * cos(rotation)

        x = x2 / ratio
        y = y2 / ratio
        if speed:
            return ["G1 F" + str(speed) + " X" + str(x) + " Y" + str(y) + ";Draw to"]
        else:
            return ["G1 F200 X" + str(x) + " Y" + str(y) + ";Draw to"]

    def turnOn(self):
        global laser_on
        laser_on = True
        return ["G4 P1", "@X9L0"]

    def turnOff(self):
        global laser_on
        laser_on = False
        return ["G4 P1", "@X9L255"]

    def turnHalf(self):
        global laser_on
        laser_on = False
        return ["G4 P1", "@X9L220"]

    def to_image(self, buffer_data, img_width, img_height):
        int_data = list(buffer_data)
        # print(int_data[:10])
        assert len(int_data) == img_width * img_height, "data length != width * height, %d != %d * %d" % (len(int_data), img_width, img_height)
        image = [int_data[i * img_width: (i + 1) * img_width] for i in range(img_height)]

        # with open('tmp.py', 'w') as f:
        #     print('a=', file=f, end='')
        #     print(image, file=f)
        #     print('import cv2', file=f)
        #     print('import numpy as np', file=f)
        #     print('b = np.array(a)', file=f)
        #     print('cv2.imwrite(\'SS.png\', b)', file=f)

        return image

    def add_image(self, buffer_data, img_width, img_height, x1, y1, x2, y2, thres):
        pix = to_image(buffer_data, img_width, img_height)
        real_width = float(x2 - x1)
        real_height = float(y1 - y2)
        for h in range(img_height):
            for w in range(img_width):
                real_x = (x1 + (real_width) * w / img_width)
                real_y = (y1 - (real_height) * h / img_height)
                if real_x ** 2 + real_y ** 2 <= self.radius ** 2:
                    if pix[h][w] < thres:
                        # [TODO]
                        # if picture is small, when mapping to image_map should add more interval points
                        # but not gonna happen in near future?
                        x_on_map = int(round(self.radius * self.pixel_per_mm + real_x / self.pixel_per_mm))
                        y_on_map = int(round(self.radius * self.pixel_per_mm + real_y / self.pixel_per_mm))
                        self.image_map[x_on_map][y_on_map] = pix[h][w]
        # alignment fail when float to int

    def gcode_generate(self):
        gcode = []

        gcode.append("@X5H2000")
        gcode.append("@X5H2000")

        #  gcode.append("M666 X-1.95 Y-0.4 Z-2.1 R97.4 H241.2")
        gcode.append("M666 X-1.95 Y-0.4 Z-2.1 R97.4 H241.2")  # new

        gcode += turnOff()
        gcode.append(";Flux image laser")
        gcode.append(";Image size:%d * %d" % (img_width, img_height))

        gcode.append("G28")
        gcode.append(";G29")

        gcode.append("G1 F3000 Z" + str(focal_l) + "")

        # pix = cv2.imread('S.png')
        # pix = cv2.cvtColor(pix, cv2.COLOR_BGR2GRAY)

        # print pix.shape
        # input()

        # offsetX = img_width / 2.
        # offsetY = img_height / 2.
        # rotation = pi / 4.
        # # ratio = 8.

        # last_i = 0
        # # gcode += ["M104 S200"]
        # gcode += turnOff()
        # gcode += turnHalf()

        # [TODO]
        # #Align process

        # for k in range(3):
        #     gcode += moveTo(0, 0, offsetX, offsetY, rotation, ratio)
        #     gcode += ["G4 P300"]
        #     gcode += moveTo(0, img_height, offsetX, offsetY, rotation, ratio)
        #     gcode += ["G4 P300"]
        #     gcode += moveTo(img_width, img_height, offsetX, offsetY, rotation, ratio)
        #     gcode += ["G4 P300"]
        #     gcode += moveTo(img_width, 0, offsetX, offsetY, rotation, ratio)
        #     gcode += ["G4 P300"]
        #     gcode += moveTo(0, 0, offsetX, offsetY, rotation, ratio)
        #     gcode += ["G4 P300"]

        #column iteration
        for h in range(0, len(image_map)):
            #row iteration
            itera = range(0, len(image_map))
            final_x = len(image_map)
            if h % 2 == 1:
                final_x = 0
                itera = reversed(range(0, len(image_map)))

            for w in itera:
                if image_map[h][w] < self.thres:
                    if not laser_on:
                        last_i = w
                        gcode += moveTo(w, h)
                        gcode += turnOn()
                else:
                    if laser_on:
                        if abs(w - last_i) < 2:  # Single dot
                            pass
                            gcode += ["G4 P100"]
                        elif final_x > 0:
                            gcode += drawTo(w, h)
                        else:
                            gcode += drawTo(w, h)
                        gcode += turnOff()

            if laser_on:
                gcode += drawTo(final_x, h)
                gcode += turnOff()

        # gcode += ["M104 S0"]
        gcode += ["G28"]

        store = False
        if store:
            with open('./S.gcode', 'w') as f:
                print("\n".join(gcode) + "\n", file=f)
                # print >> f, "\n".join(gcode) + "\n"
        else:
            pass

        return "\n".join(gcode) + "\n"

a = laser_pattern()
# laser_pattern('', 432, 198, 7.3)
