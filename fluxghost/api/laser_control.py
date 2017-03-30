
from operator import itemgetter
import math
import sympy
import logging
import itertools

logger = logging.getLogger("API.LASER_CONTROL")


class laserShowOutline(object):
    def __init__(self, positions):
        self.positions = positions
        self.speed = 3000
        self.nextPoint = True
        self.needArc = False
        self.radius = 85
        self.moveTrace = []

    def move_trace_cal(self):
        pass

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

    def calculate_cross(self, pos, idx):
        present = pos[idx]
        logger.debug('index :{}'.format(idx))

        prev = pos[-1] if idx is 0 else pos[idx-1]
        _next = pos[0] if idx+1 is len(pos) else pos[idx+1]
        logger.debug('prev :{}'.format(prev))
        logger.debug('_next :{}'.format(_next))

        if self.nextPoint:
            prev_itsections = self.round_line_Intersection(prev, present)
            logger.debug('prev_itsections :{}'.format(prev_itsections))
            if self.try_itsections(prev_itsections):
                prev_itsection = self.select_closed_point(
                                                      present, prev_itsections)
            elif self.moveTrace:
                prev_itsection = self.moveTrace[-1]
            else:
                prev_itsection = None
        else:
            prev_itsection = None
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

    def draw_arc(self, first, second):
        c = self.cal_distance(first, second)
        cosR = (2 * (self.radius**2) - c**2) / (2 * (self.radius**2))
        print('cosR :', cosR)
        rad = math.acos(cosR)
        print('rad :', rad)
        one_step = 5 * math.pi / 180
        step = one_step
        x, y = first
        while step < rad:
            new_x = (x * math.cos(one_step)) + (y * math.sin(one_step))
            new_y = (x * math.sin(-one_step)) + (y * math.cos(one_step))
            self.moveTrace.append((new_x, new_y))
            x, y = self.moveTrace[-1]
            step += one_step
            print('step :', step)

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
        self.moveTrace.append((0, -85))
        rad = 5 * math.pi / 180
        for i in range(71):
            x, y = self.moveTrace[-1]
            new_x = (x * math.cos(rad)) + (y * math.sin(rad))
            new_y = (x * math.sin(-rad)) + (y * math.cos(rad))
            self.moveTrace.append((new_x, new_y))

    def run(self):
        self.sort_positions()
        logger.debug('positions: {}'.format(self.positions))
        self.redraw_if_over_radius()
        if self.is_full_round():
            self.draw_round()
            return(self.moveTrace)
        if self.needArc:
            self.draw_arc(self.moveTrace[-1], self.moveTrace[0])
        self.moveTrace.append(self.moveTrace[0])
        return self.moveTrace
