import copy
import io
import logging

import cv2
import numpy as np
from PIL import Image
from scipy.ndimage import label

from .misc import BinaryHelperMixin, BinaryUploadHelper, OnTextMessageMixin

logger = logging.getLogger('API.IMAGE_TRACER')


def image_tracer_api_mixin(cls):
    class ImageTracerApi(OnTextMessageMixin, BinaryHelperMixin, cls):
        def __init__(self, *args, **kw):
            super().__init__(*args, **kw)
            self.cmd_mapping = {'image_trace': [self.cmd_image_trace]}

        def cmd_image_trace(self, message):
            message = message.split(' ')

            def image_trace_callback(buf):
                img = Image.open(io.BytesIO(buf)).convert('RGBA')
                result = run(img, int(message[1]))
                self.send_ok(svg=result)

            file_length = message[0]
            helper = BinaryUploadHelper(int(file_length), image_trace_callback)
            self.set_binary_helper(helper)
            self.send_json(status='continue')

    def fill(pix, pixList, rgbList, width, height, edges):
        labelledList = label(rgbList)
        for row in range(width):
            for col in range(height):
                cell = pixList[row][col]
                if labelledList[0][row][col] != 1:
                    if isEdge(labelledList, row, col, width, height):
                        edges.add((row, col))
                        cell.isBlack = True
                        global HEADROW, HEADCOL
                        if HEADROW is None:
                            HEADROW = row
                            HEADCOL = col
                else:
                    cell.isFilled = True

    class Cell:
        def __init__(self, rgb):
            # self.depth = -1 # set by floodFill
            self.rgb = rgb
            if rgb == 0:
                self.isBlack = True
            else:
                self.isBlack = False
            self.isFilled = False
            self.isNormal = True
            self.isBorder = False

    def moderateBinary(pix, width, height, threshold):
        # print('Testing if image is pure black/white...', end='')
        # print('threshold threshold', threshold)
        for x in range(width):
            for y in range(height):
                # print(pix[x, y])
                r = pix[x, y][0]
                g = pix[x, y][1]
                b = pix[x, y][2]

                if r != g or g != b:
                    if max(r, g, b) < threshold:
                        pix[x, y] = (0, 0, 0, 255)
                    else:
                        pix[x, y] = (255, 255, 255, 255)
                if r != 0 and r != 255:
                    if max(r, g, b) < threshold:
                        pix[x, y] = (0, 0, 0, 255)
                    else:
                        pix[x, y] = (255, 255, 255, 255)

        # print('Passed!!!')

        return pix

    def make2dList(rows, cols):
        a = []
        for _row in range(rows):
            a += [[0] * cols]
        return a

    def makePixList(pix, width, height):
        # print('Making pixel list...', end="")
        pixList = make2dList(width, height)
        rgbList = make2dList(width, height)
        for x in range(width):
            for y in range(height):
                r, g, b, a = pix[x, y]
                pixList[x][y] = Cell(r)
                rgbList[x][y] = r
        # print('Done!!!')
        # print('Detecting image edge...', end="")
        return pixList, rgbList

    def isEdge(labelledList, startRow, startCol, width, height):
        dirs = [[-1, 0], [0, +1], [+1, 0], [0, -1], [-1, +1], [+1, +1], [+1, -1], [-1, -1]]
        for drow, dcol in dirs:
            if startRow is None:
                startRow = 0
            if startCol is None:
                startCol = 0
            row = startRow + drow
            col = startCol + dcol
            if (row < 0 or row >= width) or (col < 0 or col >= height):
                continue
            if labelledList[0][row][col] == 1:
                return True
        return False

    # from set "edges" sort points into a path
    def sortEdges(pixList, width, height, path, edgeClone=None):
        # print('Sorting edge points...',)
        # append starting point
        if path is None:
            path = []
            startRow, startCol = HEADROW, HEADCOL
            path.append([(startRow, startCol)])

        else:
            startRow, startCol = sorted(edgeClone)[0]
            path.append([(startRow, startCol)])
        dirs = [
            [-1, 0],
            [0, +1],
            [+1, 0],
            [0, -1],
            [-1, +1],
            [+1, +1],
            [+1, -1],
            [-1, -1],
            [-2, 0],
            [0, 2],
            [2, 0],
            [0, -2],
        ]
        isDone = False
        while not isDone:
            normalEdge = False
            for i in range(8):
                drow, dcol = dirs[i]
                if startRow is None:
                    startRow = 0
                if startCol is None:
                    startCol = 0
                row = startRow + drow
                col = startCol + dcol
                if (row < 0 or row >= width) or (col < 0 or col >= height):
                    continue
                # back to starting point >> done
                if len(path[-1]) > 2 and (row, col) == path[-1][0]:
                    normalEdge = True
                    # print('Done!!!')
                    isDone = True
                    break
                # prepare for edge case
                if (row, col) in path[-1]:
                    prevRow = row
                    prevCol = col
                    continue
                # found next point, add to path
                if (row, col) in edgeClone:
                    path[-1].append((row, col))
                    startRow = row
                    startCol = col
                    normalEdge = True
                    break
            if not normalEdge:
                # edge case: cannot find next point
                # print('abnormal edge...', startRow, startCol)
                cell = pixList[row][col]
                cell.isNormal = False
                # go back to previous point look for possible path
                if len(path[-1]) >= 3 and path[-1][-3] != (startRow, startCol):
                    path[-1].append((prevRow, prevCol))
                    startRow, startCol = prevRow, prevCol
                else:  # end path somewhere other than starting point
                    isDone = True
        return path

    def distance(x1, y1, x2, y2):
        return ((abs(x1 - x2) + 0.5) ** 2 + (abs(y1 - y2) + 0.5) ** 2) ** 0.5

    # get a list of nearby pixels to check which is within radius of 'milli'
    def borderExpandDirs(milli):
        inRange = []
        r = milli * 3.779528

        for row in range(-19, 19):
            for col in range(-19, 19):
                dist = distance(0, 0, row, col)
                if (row, col) == (0, 0):
                    break
                if dist <= r:
                    inRange.append((row, col))
        return inRange

    # get a set of points which are the expanded regions
    def borderExpandList(milli, pixList, edges):
        border = set()
        dirs = borderExpandDirs(milli)
        rows = len(pixList)
        cols = len(pixList[0])
        for startRow, startCol in edges:
            for drow, dcol in dirs:
                if startRow is None:
                    startRow = 0
                if startCol is None:
                    startCol = 0
                row = startRow + drow
                col = startCol + dcol
                # out of range
                if (row < 0) or (row >= rows) or (col < 0) or (col >= cols):
                    continue
                cell = pixList[row][col]
                # point is edge or image
                if cell.isBlack:
                    continue
                # point is the white inner part of image
                if not cell.isFilled:
                    continue
                border.add((row, col))
        return border

    HEADROW = None
    HEADCOL = None

    def getPathLen(path):
        n = 0
        for row in range(len(path)):
            n += len(path[row])
        return n

    def run(originalImg, threshold=128, milli=0):
        global HEADROW, HEADCOL
        HEADROW = None
        HEADCOL = None
        edges = set()
        ratio = 0.4
        # originalImg = originalImg.point(lambda p: p > threshold and 255)
        originalWidth, originalHeight = originalImg.size
        width = int(ratio * originalWidth)
        height = int(ratio * originalHeight)

        img = originalImg.resize((width, height), Image.BILINEAR)
        pix = img.load()
        pix = moderateBinary(pix, width, height, threshold)
        pixList, rgbList = makePixList(pix, width, height)
        fill(pix, pixList, rgbList, width, height, edges)
        path = sortEdges(pixList, width, height, None, edges)
        # several path for several parts in image
        while getPathLen(path) != len(edges):
            edgeClone = copy.copy(edges)
            for row in range(len(path)):
                for points in path[row]:
                    edgeClone.discard(points)
                    # print(points)
            if len(edgeClone) == 0:
                break
            path = sortEdges(pixList, width, height, path, edgeClone)
        # fill black in the expanded region
        expEdges = borderExpandList(milli, pixList, edges)
        for row, col in expEdges:
            pix[row, col] = (0, 0, 0)

        c = []
        maxL = 0
        flag = 0

        for i in range(len(path)):
            if len(path[i]) > maxL:
                # print('dddd', i, len(path[i]))
                maxL = len(path[i])
                flag = i

        c = path[flag]

        trace = (
            '<svg width="'
            + str(originalWidth)
            + '" height="'
            + str(originalHeight)
            + '" xmlns="http://www.w3.org/2000/svg"><g><path d="M'
        )
        for i in range(len(c)):
            x, y = c[i]
            trace += str(x) + ' ' + str(y) + ' '

        trace += (
            '" fill="none" stroke-width="1px" stroke="rgb(100%, 0%, 100%)" '
            'vector-effect="non-scaling-stroke" transform="scale(2.5)" /></g></svg>'
        )

        return trace

    return ImageTracerApi
