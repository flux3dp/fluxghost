
from operator import itemgetter
from time import sleep
import numpy as np
import threading
import itertools
import logging
import socket
import queue
import math
import json

logger = logging.getLogger("API.LASER_CONTROL")

class LaserShowOutline(object):
    def __init__(self, object_height, socket, *positions):
        self.object_height = float(object_height) + 10
        self.positions = positions
        self.socket = socket
        self.running = True
        self.sendQueue = queue.Queue()
        self.recvQueue = queue.Queue()
        self.recvThread = threading.Thread(target=self.socket_recv_master)
        self.recvThread.start()
        threading.Thread(target=self.socket_send_master).start()
        threading.Thread(target=self.ping_toolhead).start()
        self.start_command = ['G28',
                         'G90',
                         'firstPoint',
                         ]
        self.end_command = ['G28']

    def gen_moveTraces(self):
        moveTraces = []
        for frame in self.positions:
            moveTrace = CalculateMoveTrace().get_move_trace(frame)
            moveTrace.insert(1, 'X2O015')
            moveTrace.append('X2O000')
            moveTraces.extend(moveTrace)
        logger.info('moveTraces :{}'.format(moveTraces))
        return moveTraces

    def trace_to_command(self, trace):
        firstPoint = trace.pop(0)
        index = self.start_command.index('firstPoint')
        self.start_command[index] = 'G0 X{} Y{} Z{} F6000'.format(
            firstPoint[0], firstPoint[1], self.object_height)

        for cmd in itertools.chain(self.start_command, trace, self.end_command):
            if isinstance(cmd, tuple):
                cmd = 'G1 X{} Y{} F3000'.format(cmd[0], cmd[1])
            yield cmd

    def recv_endline(self):
        message = []
        while self.running:
            recv = self.socket.recv(1)
            message.append(recv)
            if recv == b'\n':
                break
        return b''.join(message)

    def socket_recv_master(self):
        while self.running:
            try:
                recv = self.recv_endline()
                if recv == b'ok\n':
                    self.recvQueue.put(recv)
            except socket.timeout:
                # Prevent blocking socket
                pass

    def queue_is_empty(self, Queue):
        result = True if Queue.qsize() is 0 else False
        return result

    def is_ping(self, message):
        result = True if message == '1 PING *33' else False
        return result

    def socket_send_master(self):
        while self.running:
            if self.queue_is_empty(self.sendQueue):
                continue
            message = self.sendQueue.get()
            self.socket.send(message.encode() + b"\n")
            if self.is_ping(message):
                continue
            logger.info('sent : {}'.format(message))

    def ping_toolhead(self):
        while self.running:
            self.sendQueue.put('1 PING *33')
            sleep(1)

    def stop_running(self):
        self.running = False
        while self.recvThread.isAlive():
            sleep(0.1)

    def has_message(self, queue):
        timeoutCount = 0
        while self.queue_is_empty(queue):
            timeoutCount += 1
            sleep(0.1)
            if timeoutCount > 20:
                return False
        return True

    def send_command(self, command):
        for i in range(3):
            self.sendQueue.put(command)
            if self.has_message(self.recvQueue):
                return True
        return False

    def start(self):
        self.moveTraces = self.gen_moveTraces()

        for command in self.trace_to_command(self.moveTraces):
            if self.send_command(command):
                recv = self.recvQueue.get()
                logger.info('recv : {}'.format(recv))
            else :
                self.stop_running()
                return False

        self.stop_running()
        return True

class CalculateMoveTrace(object):
    def __init__(self):
        self.nextPoint = True
        self.needArc = False
        self.radius = 85
        self.arcStep = 10 * math.pi / 180
        self.moveTrace = []

    def try_itsections(self, intersetcions):
        for i in intersetcions:
            try:
                list(map(lambda x: float(x), i))
            except TypeError:
                return False
            return True

    def sort_positions(self):
        self.positions.sort()
        l_positions = sorted(self.positions[0:2], key=itemgetter(1))
        r_positions = sorted(
                    self.positions[2:4], key=itemgetter(1), reverse=True)
        self.positions = l_positions + r_positions

    def select_closed_point(self, ref, present, sol):
        limit = self.cal_distance(ref, present)
        first = self.cal_distance(present, sol[0])
        second = self.cal_distance(present, sol[1])
        first_with_ref = self.cal_distance(ref, sol[0])
        second_with_ref = self.cal_distance(ref, sol[1])

        # return None if two point both are not on straight line.
        present_over_limit = first > limit and second > limit
        ref_over_limit = first_with_ref > limit and second_with_ref > limit
        if present_over_limit or ref_over_limit:
            self.nextPoint = False
            return None

        self.nextPoint = True
        point = sol[1] if first > second else sol[0]
        return point

    def round_line_Intersection(self, first, second):
        # if straight line perpendicular to X.
        if first[0] == second[0]:
            x = first[0]

            # if out of Circle's range.
            if self.radius**2 - x**2 < 0:
                return (None, None)

            y = math.sqrt(self.radius**2 - x**2)
            sol = [(x, y), (x, -y)]
            return sol

        else:
            # get equation of straight line from two given position.
            a = np.mat([[first[0], 1],
                        [second[0], 1]])
            b = np.mat([first[1], second[1]]).T
            r = np.linalg.solve(a,b)
            a, b = map(float, r)

            A = 1 + a**2
            B = 2 * a * b
            C = b**2 - self.radius**2

            if B**2 - 4*A*C < 0:
                return (None, None)

            # first intersetcion (x, y)
            x = (-B + math.sqrt(B**2 - 4*A*C)) / (2*A)
            y = a*x + b
            sol = [(x, y)]

            # second intersetcion (x, y)
            x = (-B - math.sqrt(B**2 - 4*A*C)) / (2*A)
            y = a*x + b
            sol.append((x, y))
            return sol

    def cal_prev_itsection(self, prev, present):
        prev_itsections = self.round_line_Intersection(prev, present)
        logger.debug('prev_itsections :{}'.format(prev_itsections))
        if self.try_itsections(prev_itsections):
            prev_itse = self.select_closed_point(prev, present, prev_itsections)
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
        logger.debug('nextPoint: {}'.format(self.nextPoint))
        prev_itsection = cal_prev(prev, present) if self.nextPoint else None
        logger.debug('prev_itsection :{}'.format(prev_itsection))

        next_itsections = self.round_line_Intersection(present, _next)
        logger.debug('next_itsections :{}'.format(next_itsections))

        if self.try_itsections(next_itsections):
            # force sympy.sqrt() turn to float type
            # that can prevent incorrect point acquire.
            next_itsections = [tuple(map(float, i)) for i in next_itsections]
            next_itsection = self.select_closed_point(_next, present, next_itsections)
        else:
            next_itsection = None
            self.nextPoint = False

        return prev_itsection, next_itsection

    def over_radius(self, point):
        return math.hypot(point[0], point[1]) >= self.radius

    def cal_distance(self, first, second):
        """
        calculate distance between two point.
        """
        d = math.sqrt(math.pow(first[0] - second[0], 2) +
                      math.pow(first[1] - second[1], 2))
        return d

    def quadrant_jadge(self, point):
        x, y = point
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

            self.moveTrace.append((float(new_x), float(new_y)))
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

    def get_move_trace(self, positions):
        self.__init__()
        self.positions = json.loads(positions)
        self.run()
        return self.moveTrace
