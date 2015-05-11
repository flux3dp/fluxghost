# !/usr/bin/env python3
from math import pi, sin, cos
# import cv2
laser_on = False


def to_image(buffer_data, img_width, img_height):
    int_data = list(buffer_data)
    print(int_data[:10])
    assert len(int_data) == img_width * img_height, "data length != width * height, %d != %d * %d" % (len(int_data), img_width, img_height)
    image = [int_data[i * img_width: (i + 1) * img_width] for i in range(img_height)]
    return image


def rxy(x, y):
    return


def moveTo(x, y, offsetX, offsetY, rotation, ratio):
    x -= offsetX
    y -= offsetY
    x2 = x * cos(rotation) + y * sin(rotation)
    y2 = x * -sin(rotation) + y * cos(rotation)
    return ["G1 F600 X" + str((x2) / ratio) + " Y" + str((y2) / ratio)]


def drawTo(x, y, offsetX, offsetY, rotation, ratio, slow=False):
    x -= offsetX
    y -= offsetY
    x2 = x * cos(rotation) + y * sin(rotation)
    y2 = x * -sin(rotation) + y * cos(rotation)
    if slow:
        return ["G1 F50 X" + str((x2) / ratio) + " Y" + str((y2) / ratio) + ";Draw to"]
    else:
        return ["G1 F200 X" + str((x2) / ratio) + " Y" + str((y2) / ratio) + ";Draw to"]


def turnOn():
    global laser_on
    laser_on = True
    return ["G4 P1", "@X9L0"]


def turnOff():
    global laser_on
    laser_on = False
    return ["G4 P1", "@X9L255"]


def turnHalf():
    global laser_on
    laser_on = False
    return ["@X9L220"]


def laser_pattern(buffer_data, img_width, img_height, ratio):
    gcode = []
    # print(buffer_data)

    gcode.append("@X5H2000")
    gcode.append("M666 X-1.95 Y-0.4 Z-2.1 R97.4 H241.2")
    gcode.append(";Flux image laser")
    gcode.append(";Image size:%d * %d" % (img_width, img_height))

    gcode.append("G28")
    gcode.append(";G29")
    gcode.append("G1 F3000 Z11")

    pix = to_image(buffer_data, img_width, img_height)
    # pix = cv2.imread('S.png')
    # pix = cv2.cvtColor(pix, cv2.COLOR_BGR2GRAY)

    # print pix.shape
    # input()

    offsetX = img_width / 2.
    offsetY = img_height / 2.
    rotation = pi / 4.
    # ratio = 6.

    # pixel_size = 100 / ratio

    last_i = 0
    gcode += turnOff()
    # gcode += ["M104 S200"]
    gcode += turnOff()
    gcode += turnHalf()

    #Align process
    for k in range(3):
        gcode += moveTo(0, 0, offsetX, offsetY, rotation, ratio)
        gcode += ["G4 P300"]
        gcode += moveTo(0, img_height, offsetX, offsetY, rotation, ratio)
        gcode += ["G4 P300"]
        gcode += moveTo(img_width, img_height, offsetX, offsetY, rotation, ratio)
        gcode += ["G4 P300"]
        gcode += moveTo(img_width, 0, offsetX, offsetY, rotation, ratio)
        gcode += ["G4 P300"]
        gcode += moveTo(0, 0, offsetX, offsetY, rotation, ratio)
        gcode += ["G4 P300"]

    #column iteration
    for h in range(0, img_height):
        #row iteration
        itera = range(0, img_width)
        final_x = img_width
        if h % 2 == 1:
            final_x = 0
            itera = reversed(range(0, img_width))

        for w in itera:
            if pix[h][w] < 50:
                if not laser_on:
                    last_i = w
                    gcode += moveTo(w, h, offsetX, offsetY, rotation, ratio)
                    gcode += turnOn()
            else:
                if laser_on:
                    if abs(w - last_i) < 2:  # Single dot
                        pass
                        gcode += ["G4 P100"]
                    elif final_x > 0:
                        gcode += drawTo(w - 1 / 2, h, offsetX, offsetY, rotation, ratio, abs(w - last_i) < 10)
                    else:
                        gcode += drawTo(w + 1 / 2, h, offsetX, offsetY, rotation, ratio, abs(w - last_i) < 10)
                    gcode += turnOff()

        if laser_on:
            gcode += drawTo(final_x, h, offsetX, offsetY, rotation, ratio)
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

# laser_pattern('', 200, 352, 4)
