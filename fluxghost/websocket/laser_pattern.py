from math import pi, sin, cos

def to_image(buffer_data, img_width, img_height):
  int_data = list(buffer_data)
  print(type(int_data), type(int_data[0]))
  image = [int_data[i * img_width:(i+1) * img_width] for i in range(img_height)]
  return image

def rxy(x,y):
    return 

def moveTo(x, y, offsetX, offsetY, rotation, ratio):
  x -= offsetX
  y -= offsetY
  x2 = x * cos(rotation) + y*sin(rotation)
  y2 = x * -sin(rotation) + y * cos(rotation)
  return ["G1 F600 X"+str((x2) / ratio)+" Y"+str((y2) / ratio)]

def drawTo(x, y, offsetX, offsetY, rotation, ratio, slow=False):
  x -= offsetX
  y -= offsetY
  x2 = x*cos(rotation)+y*sin(rotation)
  y2 = x*-sin(rotation)+y*cos(rotation)
  if slow:
    return ["G1 F50 X"+str((x2) / ratio)+" Y"+str((y2) / ratio)+";Draw to"]
  else:
    return ["G1 F200 X"+str((x2) / ratio)+" Y"+str((y2) / ratio)+";Draw to"]

def turnOn(laser_on):
  laser_on = True
  return ["G4 P1", "M106 S0"]

def turnOff(laser_on):
  laser_on = False
  return ["G4 P1", "M106 S255"]

def turnHalf(laser_on):
  laser_on = False
  return ["M106 S252"]

def laser_pattern(buffer_data, img_width, img_height, ratio):
  gcode = []
  gcode.append(";Flux image laser")
  gcode.append("G28")
  gcode.append(";G29")
  gcode.append("G1 F900 Z100")

  pix = to_image(buffer_data, img_width, img_height)

  # im = Image.open("taiwan.png") #Can be many different formats.
  # pix = im.load()
  gcode.append("; image size:%d * %d" % (img_width, img_height))
  
  laser_on = False

  offsetX = img_width / 2.
  offsetY = img_height / 2.
  rotation = pi/4.
  pixel_size = 1 / ratio

  

  last_i = 0
  gcode += turnOff(laser_on)
  gcode["M104 S200"]
  gcode += turnOff(laser_on) 

  gcode += turnHalf(laser_on)

  #Align process
  for k in range(5):
    gcode += moveTo(0,0, offsetX, offsetY, rotation, ratio)
    gcode += ["G4 P300"]
    gcode += moveTo(0,img_height, offsetX, offsetY, rotation, ratio)
    gcode += ["G4 P300"]
    gcode += moveTo(img_width,img_height, offsetX, offsetY, rotation, ratio)
    gcode += ["G4 P300"]
    gcode += moveTo(img_width,0, offsetX, offsetY, rotation, ratio)
    gcode += ["G4 P300"]
    gcode += moveTo(0,0, offsetX, offsetY, rotation, ratio)
    gcode += ["G4 P300"]

  #column iteration
  for j in range(0,img_height):
    #row iteration
    itera = range(0,img_width)
    final_x = img_width
    if j % 2 == 1:
      final_x = 0
      itera = reversed(range(0,img_width))

    for i in itera:
      if pix[i][j] < 50:
        if not laser_on:
          last_i = i
          gcode += moveTo(i,j, offsetX, offsetY, rotation, ratio)
          gcode += turnOn(laser_on)
      else:
        if laser_on:
          if abs(i-last_i)<2: #Single dot
            pass
            gcode += ["G4 P100"]
          elif final_x > 0:
            gcode += drawTo(i - 1/2,j, offsetX, offsetY, rotation, ratio, abs(i-last_i) < 10)
          else:
            gcode += drawTo(i + 1/2,j, offsetX, offsetY, rotation, ratio, abs(i-last_i) < 10)
          gcode += turnOff(laser_on)

    if laser_on:
      gcode += drawTo(final_x,j, offsetX, offsetY, rotation, ratio)
      gcode += turnOff(laser_on)

  gcode += ["M104 S0"]
  gcode += ["G28"]
  return "\n".join(gcode)+"\n"

# print(laser_pattern(b"\xff\x80\x79\x00" ,2,2,1))