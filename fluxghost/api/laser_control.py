
from operator import itemgetter
import math
import sympy
import logging

logger = logging.getLogger("API.LASER_CONTROL")


class laserShowOutline(object):
    def __init__(self, positions):
        self.positions = positions
        self.speed = 3000
        self.nextPoint = True
        self.needArc = False
        self.radius = 85
        self.arcStep = 5 * math.pi / 180
        self.moveTrace = []

    def try_itsections(self, intersetcions):
        for i in intersetcions:
            try:
                list(map(lambda x: float(x), i))
            except TypeError:
                return False
            return True

    def sort_positions(self):
        split = lambda s: list(map(float, s.split(',')))
        self.positions = list(map(split, self.positions))
        self.positions.sort()
        l_positions = sorted(self.positions[0:2], key=itemgetter(1))
        r_positions = sorted(
                    self.positions[2:4], key=itemgetter(1), reverse=True)
        self.positions = l_positions + r_positions

    def select_closed_point(self, first, sol):
        distance = math.sqrt(math.pow(first[0] - sol[0][0], 2) +
                             math.pow(first[1] - sol[0][1], 2))
        distance1 = math.sqrt(math.pow(first[0] - sol[1][0], 2) +
                              math.pow(first[1] - sol[1][1], 2))
        if distance > distance1:
            return sol[1]
        else:
            return sol[0]

    def round_line_Intersection(self, first, second):
        x = sympy.Symbol('x')
        y = sympy.Symbol('y')
        if first[0] - second[0] == 0:
            f1 = first[0] - x
        else:
            m = (first[1] - second[1]) / (first[0] - second[0])
            f1 = ((first[1] - y) / (first[0] - x)) - m
        f2 = (x**2) + (y**2) - (self.radius**2)
        sol = sympy.solve((f1, f2), x, y)
        return sol

    def cal_prev_itsection(self, prev, present):
        prev_itsections = self.round_line_Intersection(prev, present)
        logger.debug('prev_itsections :{}'.format(prev_itsections))
        if self.try_itsections(prev_itsections):
            prev_itse = self.select_closed_point(present, prev_itsections)
        elif self.moveTrace:
            prev_itse = self.moveTrace[-1]
        else:
            prev_itse = None
        return prev_itse

    def calculate_cross(self, pos, idx):
        present = pos[idx]
        logger.debug('index :{}'.format(idx))

        prev = pos[-1] if idx is 0 else pos[idx-1]
        _next = pos[0] if idx+1 is len(pos) else pos[idx+1]
        logger.debug('prev :{}'.format(prev))
        logger.debug('_next :{}'.format(_next))

        cal_prev = self.cal_prev_itsection
        prev_itsection = cal_prev(prev, present) if self.nextPoint else None
        logger.debug('prev_itsection :{}'.format(prev_itsection))

        next_itsections = self.round_line_Intersection(present, _next)
        logger.debug('next_itsections :{}'.format(next_itsections))

        if self.try_itsections(next_itsections):
            next_itsection = self.select_closed_point(present, next_itsections)
            self.nextPoint = True
        else:
            next_itsection = None
            self.nextPoint = False

        return prev_itsection, next_itsection

    def over_radius(self, point):
        return math.hypot(point[0], point[1]) >= self.radius

    def cal_distance(self, first, second):
        d = math.sqrt(math.pow(first[0] - second[0], 2) +
                      math.pow(first[1] - second[1], 2))
        return d

    def quadrant_jadge(self, point):
        x = point[0]
        y = point[1]
        rad = math.acos(abs(x) / self.radius)
        if x >= 0 and y >= 0:
            quadrant_arc = rad
        elif x < 0 and y >= 0:
            quadrant_arc = math.pi / 2 + ((math.pi / 2) - rad)
        elif x < 0 and y < 0:
            quadrant_arc = math.pi + rad
        elif x >= 0 and y < 0:
            quadrant_arc = 3 * math.pi / 2 + ((math.pi / 2) - rad)
        return quadrant_arc

    def draw_arc(self, first, second):
        arc_first = self.quadrant_jadge(first)
        logger.debug('first rad:{}'.format(math.degrees(arc_first)))
        arc_second = self.quadrant_jadge(second)
        logger.debug('second rad:{}'.format(math.degrees(arc_second)))
        rad = arc_first - arc_second
        rad = 2 * math.pi + rad if rad < 0 else rad
        logger.debug('rad :{}'.format(rad))

        stepped = step = self.arcStep
        x, y = first
        while stepped < rad:
            new_x = (x * math.cos(step)) + (y * math.sin(step))
            new_y = (x * math.sin(-step)) + (y * math.cos(step))
            self.moveTrace.append((new_x, new_y))
            x, y = self.moveTrace[-1]
            stepped += step

    def redraw_if_over_radius(self):
        for index in range(len(self.positions)):
            present = self.positions[index]
            logger.debug('present :{}'.format(present))

            if not self.over_radius(present):
                self.moveTrace.append(tuple(present))
                continue

            prev, _next = self.calculate_cross(self.positions, index)
            logger.debug('prev :{}, _next:{}'.format(prev, _next))

            if prev:
                self.moveTrace.append(prev)
            if _next:
                if self.moveTrace:
                    self.draw_arc(self.moveTrace[-1], _next)
                else:
                    self.needArc = True
                self.moveTrace.append(_next)
            logger.debug('moveTrace :{}'.format(self.moveTrace))

    def is_full_round(self):
        return not self.moveTrace

    def draw_round(self):
        self.moveTrace.append((0, -self.radius))
        loop = (2 * math.pi / self.arcStep) - 1
        for i in range(int(loop)):
            x, y = self.moveTrace[-1]
            n_x = (x * math.cos(self.arcStep)) + (y * math.sin(self.arcStep))
            n_y = (x * math.sin(-self.arcStep)) + (y * math.cos(self.arcStep))
            self.moveTrace.append((n_x, n_y))

    def run(self):
        self.sort_positions()
        logger.debug('positions: {}'.format(self.positions))
        self.redraw_if_over_radius()
        if self.is_full_round():
            self.draw_round()

        if self.needArc:
            self.draw_arc(self.moveTrace[-1], self.moveTrace[0])
        self.moveTrace.append(self.moveTrace[0])
        return self.moveTrace
