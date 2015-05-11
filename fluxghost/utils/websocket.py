
import threading
import socket
import struct
import errno


# WebSocket Frame Flag
FIN_FLAG = 0x8000
RSVs_FLAG = 0x7000
OPCODE_FLAG = 0x0F00
MASK_FLAG = 0x0080
PAYLOAD_FLAG = 0x007F

# WebSocket OpCode
CONT_FRAME = 0x0
TEXT_FRAME = 0x1
BINARY_FRAME = 0x2
CLOSE_FRAME = 0x8
PING_FRAME = 0x9
PONG_FRAME = 0xa


# WebSocket closing frame status codes
class STATUS:
    NORMAL = 1000
    GOING_AWAY = 1001
    PROTOCOL_ERROR = 1002
    UNSUPPORTED_DATA_TYPE = 1003
    NOT_AVAILABLE = 1005
    ABNORMAL_CLOSED = 1006
    INVALID_PAYLOAD = 1007
    POLICY_VIOLATION = 1008
    MESSAGE_TOO_BIG = 1009
    INVALID_EXTENSION = 1010
    UNEXPECTED_CONDITION = 1011
    TLS_HANDSHAKE_ERROR = 1015


# Handler Reciver Flag
WAIT_LARGE_DATA = 0x40
HAS_FRAGMENT_FLAG = 0x80


MAX_FRAME_SIZE = 2**20
BUFFER_SIZE = 4096
MAGIC_STRING = '258EAFA5-E914-47DA-95CA-C5AB0DC85B11'

"""
About WebSocketHandler:
  WebSocketHandler implement WebSocket protocol with RFC 6455 only. It is not
  support old WebSocket protocol.


  0                   1                   2                   3
  0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
 +-+-+-+-+-------+-+-------------+-------------------------------+
 |F|R|R|R| opcode|M| Payload len |    Extended payload length    |
 |I|S|S|S|  (4)  |A|     (7)     |             (16/64)           |
 |N|V|V|V|       |S|             |   (if payload len==126/127)   |
 | |1|2|3|       |K|             |                               |
 +-+-+-+-+-------+-+-------------+ - - - - - - - - - - - - - - - +
 |     Extended payload length continued, if payload len == 127  |
 + - - - - - - - - - - - - - - - +-------------------------------+
 |                               |Masking-key, if MASK set to 1  |
 +-------------------------------+-------------------------------+
 | Masking-key (continued)       |          Payload Data         |
 +-------------------------------- - - - - - - - - - - - - - - - +
 :                     Payload Data continued ...                :
 + - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - +
 |                     Payload Data continued ...                |
 +---------------------------------------------------------------+
"""


class WebSocketHandler(object):
    def __init__(self, request, client, server, **options):
        self.request = request
        self.client_address = client
        self.server = server
        self._mutex_websocket = threading.Lock()
        self.running = True
        self._is_closing = False
        self._is_closed = False
        self.buffer = bytearray(BUFFER_SIZE)
        self.recv_flag = 0
        self.recv_offset = 0
        self.buf_view = memoryview(self.buffer)
        self.fragments = None

    def fileno(self):
        return self.request.fileno()

    def doRecv(self):
        if self._is_closed:
            raise socket.error(errno.ECONNRESET, 'WebSocket is closed')

        buf = (self.recv_flag & WAIT_LARGE_DATA == 0) and \
            self.buf_view[self.recv_offset:] or \
            self.ext_buf_view[self.ext_recv_offset:]

        length = self.request.recv_into(buf)
        if length == 0:
            raise socket.error(errno.ECONNRESET, 'Connection reset')

        if self.recv_flag & WAIT_LARGE_DATA == 0:
            self.recv_offset += length
        else:
            self.ext_recv_offset += length

        try:
            while self._handleBuffer():
                pass
        except WebsocketError:
            self.request.close()
            raise

    def _handleBuffer(self):
        # Return True if buffer has data left inside
        if (self.recv_flag & WAIT_LARGE_DATA) == 0:
            # Handle message less then BUFFER_SIZE
            if self.recv_offset < 6:
                return False

            (flags, ) = struct.unpack('>H', self.buffer[:2])
            flag_payload = flags & PAYLOAD_FLAG

            # ref: Calculate message lenght according to RFC 6455 (Chp 5-2)
            fullsize = 6
            payload_len = flag_payload

            if flag_payload == 126:
                payload_len = struct.unpack('>H', self.buffer[2:4])[0]
                fullsize += (payload_len + 2)
            elif flag_payload == 127:
                if self.recv_offset < 10:
                    return
                payload_len = struct.unpack('>Q', self.buffer[2:10])[0]
                fullsize += (payload_len + 8)
            else:
                fullsize += payload_len

            if fullsize < BUFFER_SIZE:
                if self.recv_offset >= fullsize:
                    self._handleMessageFrame(self.buf_view[:fullsize])
                    self.buf_view[:(self.recv_offset - fullsize)] = \
                        self.buf_view[fullsize:self.recv_offset]
                    self.recv_offset -= fullsize
                    return (self.recv_offset > 0)
            else:
                self.recv_flag |= WAIT_LARGE_DATA
                self.ext_buffer = bytearray(fullsize)
                self.ext_buffer[:self.recv_offset] = \
                    self.buffer[:self.recv_offset]
                self.ext_recv_offset = self.recv_offset
                self.ext_buf_view = memoryview(self.ext_buffer)
        else:
            # Handle message larger then BUFFER_SIZE
            if self.ext_recv_offset == len(self.ext_buffer):
                self._handleMessageFrame(self.ext_buf_view)
                self.ext_buffer = None
                self.ext_recv_offset = None
                self.ext_buf_view = None

                self.recv_flag ^= WAIT_LARGE_DATA
                self.recv_offset = 0

        return False

    def _handleMessageFrame(self, memview):
        (flags, ) = struct.unpack('>H', memview[:2])

        flag_fin = flags & FIN_FLAG
        flag_rsv = flags & RSVs_FLAG
        flag_opcode = flags & OPCODE_FLAG
        flag_mask = flags & MASK_FLAG
        flag_payload = flags & PAYLOAD_FLAG

        try:
            assert flag_rsv == 0, "flag_rsv must be 0 but get %i" % flag_rsv
            assert flag_mask == MASK_FLAG, ("flag_mask must be %i but get %i" %
                                            (MASK_FLAG, flag_mask))
        except AssertionError as e:
            raise WebsocketError(e.args[0])

        body_offset = 2
        if flag_payload == 126:
            body_offset = 4
        elif flag_payload == 127:
            body_offset = 10

        mask = memview[body_offset:body_offset + 4]
        data = memview[body_offset + 4:]

        self._unmaskData(mask, data)

        has_fragement = self.recv_flag & HAS_FRAGMENT_FLAG

        if flag_fin and (not has_fragement):
            try:
                self._handleMessage((flag_opcode >> 8), data.tobytes())
            finally:
                pass
        else:
            if not has_fragement:
                self.fragments = [data.tobytes()]
                self.fragments_opcode = (flag_opcode >> 8)
                self.recv_flag |= HAS_FRAGMENT_FLAG
            else:
                self.fragments.append(data.tobytes())

                if flag_fin:
                    try:
                        self._handleMessage(self.fragments_opcode,
                                            ''.join(self.fragments))
                    finally:
                        self.fragments = None
                        self.recv_flag ^= HAS_FRAGMENT_FLAG

    def _handleMessage(self, opcode, message):
        # ref: opcode in RFC 6455 (Chp 5.5)
        if opcode != 0x8 and not self.running:
            raise socket.error(errno.ECONNRESET, 'WebSocket is closed')
        elif opcode == 0x1:
            self.onMessage(message.decode("utf8"), False)
        elif opcode == 0x2:
            self.onMessage(message, True)
        elif opcode == 0x8:
            self.onClose(message)
        elif opcode == 0x9:
            self.onPing(message)
        elif opcode == 0xa:
            self.onPong(message)

    def _unmaskData(self, mask, data):
        # TODO: Fix performance, it is very slow now
        length = len(data)
        offset = 0
        shift = 0

        while offset < length:
            data[offset] = data[offset] ^ mask[shift]
            offset += 1
            shift = ((shift < 3) and (shift + 1) or 0)

    def _send(self, opcode, message):
        if self._is_closing:
            raise socket.error(errno.ECONNRESET, 'WebSocket is closed')

        offset = 0
        length = len(message)
        buf = memoryview(message)

        if length > 524288:
            raise Exception("WebSocketHandler can not send message larger "
                            "then 524288, it is a bug! :)")

        while offset < length:
            flag = l = 0

            if offset == 0:  # first frame
                flag += (opcode << 8)

            if offset + MAX_FRAME_SIZE >= length:  # last frame
                flag += FIN_FLAG
                l = length - offset
            else:
                l = MAX_FRAME_SIZE

            if l < 126:
                self.request.send(struct.pack('>H', flag + l))
            elif l < 2**16:
                self.request.send(struct.pack('>HH', flag + 126, l))
            elif l < 2**64:
                self.request.send(struct.pack('>HQ', flag + 127, l))
            else:
                raise Exception("WebSocketHandler can not send message larger"
                                " then %i, it is a bug! :)" % (2**64))

            ll = l
            while ll > 0:
                dl = self.request.send(buf[offset:offset + ll])
                ll -= dl

            offset += l

    def _closed(self):
        self.request.close()

    def onClose(self, message):
        if not self._is_closing:
            # Remote send close message, response and close it
            with self._mutex_websocket:
                if self.running:
                    self.running = False
                    self._send(CLOSE_FRAME, message)

            self._is_closing = True

        self._is_closing = True
        self._is_closed = True
        self.running = False

        self._closed()

    def onPing(self, message):
        self._send(PONG_FRAME, message)

    def onPong(self, message):
        pass

    def onMessage(self, message, is_binary):
        pass

    def send(self, message, is_binary=False):
        with self._mutex_websocket:
            if is_binary:
                self._send(BINARY_FRAME, message)
            else:
                self._send(TEXT_FRAME, message.encode())

    def send_text(self, message):
        with self._mutex_websocket:
            self._send(TEXT_FRAME, message.encode())

    def send_binary(self, buf):
        with self._mutex_websocket:
            self._send(BINARY_FRAME, buf)

    def ping(self, data):
        self._send(PING_FRAME, data)

    def close(self, code=STATUS.NORMAL, message=""):
        # RFC 6455: If there is a body, the first two bytes of the body MUST be
        # a 2-byte unsigned integer
        buffer = struct.pack('>H', code) + message.encode()

        with self._mutex_websocket:
            if self.running:
                self._send(CLOSE_FRAME, buffer)
                self.request.shutdown(socket.SHUT_WR)
                self._is_closing = True


class WebsocketError(Exception):
    pass
