from datetime import datetime
from getpass import getuser
import logging
import io
import numpy as np
from PIL import Image, ImageEnhance

import cv2
from math import radians, degrees, cos, sin
from pprint import pprint

from .misc import BinaryUploadHelper, BinaryHelperMixin, OnTextMessageMixin

logger = logging.getLogger("API.IMAGE_TRACER")

def image_tracer_api_mixin(cls):
    class ImageTracerApi(OnTextMessageMixin, BinaryHelperMixin, cls):

        def __init__(self, *args, **kw):
            super(ImageTracerApi, self).__init__(*args, **kw)
            self.cmd_mapping = {
                'image_trace': [self.cmd_image_trace],
                'basic_processing': [self.cmd_basic_processing],
            }

        def cmd_image_trace(self, message):
            message = message.split(" ")
            def image_trace_callback(buf):
                img = Image.open(io.BytesIO(buf))
                result = getImageTraceSvg(img, float(message[1]), float(message[2]), 255-int(message[3]))
                self.send_ok(svg = result)

            file_length = message[0]
            helper = BinaryUploadHelper(int(file_length), image_trace_callback)
            self.set_binary_helper(helper)
            self.send_json(status="continue")

        def cmd_basic_processing(self, message):
            message = message.split(" ")
            def basic_processing_callback(buf):
                img = Image.open(io.BytesIO(buf)).convert('LA')
                result = basicProcessing(img, float(message[1]), float(message[2]))
                self.send_binary(result)
                self.send_ok()
            
            file_length = message[0]
            helper = BinaryUploadHelper(int(file_length), basic_processing_callback)
            self.set_binary_helper(helper)
            self.send_json(status="continue")

    def getImageTraceSvg(img, brightness = 1, contrast = 1, thresholdValue = 90):
        print('b,c,t :', brightness, contrast, thresholdValue)

        img_cv = np.array(img)

        for i in range(img_cv.shape[0]):
            for j in range(img_cv.shape[1]):
                '''
                flag = True
                for k in range(4):
                    if img_cv[i][j][k] != 0:
                        flag = False
                        break
                if flag == True:
                '''
                if img_cv[i][j][0] == img_cv[i][j][1] == img_cv[i][j][2] == img_cv[i][j][3] == 0:
                    img_cv[i][j] = img_cv[i][j] + 255 * np.ones(4, np.uint8)

        gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
        img_cv = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)

        img = Image.fromarray(img_cv)
        img = ImageEnhance.Brightness(img).enhance(brightness)
        img = ImageEnhance.Contrast(img).enhance(contrast)

        img_cv = np.array(img)
        gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)

        gradX = cv2.Sobel(gray, ddepth=cv2.CV_32F, dx=1, dy=0, ksize=-1)
        gradY = cv2.Sobel(gray, ddepth=cv2.CV_32F, dx=0, dy=1, ksize=-1)

        # subtract the y-gradient from the x-gradient
        gradient = cv2.subtract(gradX, gradY)
        gradient = cv2.convertScaleAbs(gradient)

        # blur and threshold the image
        # blurred = cv2.blur(gradient, (9, 9))
        (_, thresh) = cv2.threshold(gradient, thresholdValue, 255, cv2.THRESH_BINARY)

        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 25))
        closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
        # perform a series of erosions and dilations
        closed = cv2.erode(closed, None, iterations=4)
        closed = cv2.dilate(closed, None, iterations=4)

        img_cv,cnts,hierarchy = cv2.findContours(closed.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)

        if len(cnts) is 0:
            return
        c = max(cnts, key=cv2.contourArea) #max contour
        trace = "<svg width=\""+str(img_cv.shape[1])+"\" height=\""+str(img_cv.shape[0])+"\" xmlns=\"http://www.w3.org/2000/svg\"><path style=\"fill: none; stroke-width: 1px; stroke: black;\" d=\"M"
        for i in range(len(c)):
            x, y = c[i][0]
            trace += (str(x) +  ' ' + str(y) +' ')

        trace += "\"/></svg>"

        return trace

    def basicProcessing(img, brightness = 1, contrast = 1):

        img = ImageEnhance.Brightness(img).enhance(brightness)
        img = ImageEnhance.Contrast(img).enhance(contrast)

        img_io = io.BytesIO()
        img.save(img_io, 'PNG')

        return img_io.getbuffer()

    return ImageTracerApi
