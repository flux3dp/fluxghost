
import socket
import struct
import errno


# Following is define in RFC 6455
# WebSocket Frame Flag
FLAG_FIN = 0x8000
FLAG_RSVs = 0x7000
FLAG_OPCODE= 0x0F00
FLAG_MASK = 0x0080
FLAG_PAYLOAD = 0x007F

# WebSocket OpCode
FRAME_CONT = 0x0
FRAME_TEXT = 0x1
FRAME_BINARY = 0x2
FRAME_CLOSE = 0x8
FRAME_PING = 0x9
FRAME_PONG = 0xa

# WebSocket Close Status
ST_NORMAL = 1000
ST_GOING_AWAY = 1001
ST_PROTOCOL_ERROR = 1002
ST_UNSUPPORTED_DATA_TYPE = 1003
ST_NOT_AVAILABLE = 1005
ST_ABNORMAL_CLOSED = 1006
ST_INVALID_PAYLOAD = 1007
ST_POLICY_VIOLATION = 1008
ST_MESSAGE_TOO_BIG = 1009
ST_INVALID_EXTENSION = 1010
ST_UNEXPECTED_CONDITION = 1011
ST_TLS_HANDSHAKE_ERROR = 1015


# Following is software environment
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
        self.running = True
        self._is_closing = False
        self.buffer = bytearray(BUFFER_SIZE)
        self.recv_flag = 0
        self.recv_offset = 0
        self.buf_view = memoryview(self.buffer)
        self.fragments = None

    def fileno(self):
        return self.request.fileno()

    def do_recv(self):
        buf = (self.recv_flag & WAIT_LARGE_DATA == 0) and \
            self.buf_view[self.recv_offset:] or \
            self.ext_buf_view[self.ext_recv_offset:]

        length = self.request.recv_into(buf)
        if length == 0:
            self._closed()
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
            flag_payload = flags & FLAG_PAYLOAD

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
                    self._handle_message_frame(self.buf_view[:fullsize])
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
                self._handle_message_frame(self.ext_buf_view)
                self.ext_buffer = None
                self.ext_recv_offset = None
                self.ext_buf_view = None

                self.recv_flag ^= WAIT_LARGE_DATA
                self.recv_offset = 0

        return False

    def _handle_message_frame(self, memview):
        (flags, ) = struct.unpack('>H', memview[:2])

        flag_fin = flags & FLAG_FIN
        flag_rsv = flags & FLAG_RSVs
        flag_opcode = flags & FLAG_OPCODE
        flag_mask = flags & FLAG_MASK
        flag_payload = flags & FLAG_PAYLOAD

        try:
            assert flag_rsv == 0, "flag_rsv must be 0 but get %i" % flag_rsv
            assert flag_mask == FLAG_MASK, ("flag_mask must be %i but get %i" %
                                            (FLAG_MASK, flag_mask))
        except AssertionError as e:
            raise WebsocketError(e.args[0])

        body_offset = 2
        if flag_payload == 126:
            body_offset = 4
        elif flag_payload == 127:
            body_offset = 10

        mask = memview[body_offset:body_offset + 4]
        data = memview[body_offset + 4:]

        self._unmask_data(mask, data)

        has_fragement = self.recv_flag & HAS_FRAGMENT_FLAG

        if flag_fin and (not has_fragement):
            try:
                self._handle_message((flag_opcode >> 8), data.tobytes())
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
                        self._handle_message(self.fragments_opcode,
                                            b''.join(self.fragments))
                    finally:
                        self.fragments = None
                        self.recv_flag ^= HAS_FRAGMENT_FLAG

    def _handle_message(self, opcode, message):
        # ref: opcode in RFC 6455 (Chp 5.5)
        if opcode == 0x1:
            self.on_text_message(message.decode("utf8"))
        elif opcode == 0x2:
            self.on_binary_message(message)
        elif opcode == 0x8:
            self.on_close(message)
        elif opcode == 0x9:
            self.on_ping(message)
        elif opcode == 0xa:
            self.on_pong(message)

    def _unmask_data(self, mask, data):
        # TODO: Fix performance, it is very slow now
        length = len(data)
        offset = 0
        shift = 0

        while offset < length:
            data[offset] = data[offset] ^ mask[shift]
            offset += 1
            shift = ((shift < 3) and (shift + 1) or 0)

    def _send(self, opcode, message):
        if self._is_closing and opcode != FRAME_CLOSE:
            raise socket.error(errno.ECONNRESET, 'WebSocket is closed')

        offset = 0
        length = len(message)
        buf = memoryview(message)

        while offset < length:
            flag = l = 0

            if offset == 0:  # first frame
                flag += (opcode << 8)

            if offset + MAX_FRAME_SIZE >= length:  # last frame
                flag += FLAG_FIN
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
                raise Exception("Can not send message larger then %i" %
                                (2**64))

            ll = l
            while ll > 0:
                dl = self.request.send(buf[offset:offset + 4096])
                ll -= dl

            offset += l

    def _closed(self):
        self.request.close()
        self.running = False

    def on_close(self, message):
        if not self._is_closing:
            # Remote send close message, response and close it.
            self._is_closing = True
            self._send(FRAME_CLOSE, b'\x03\xe8')
            self.request.shutdown(socket.SHUT_WR)

        self._closed()

    def on_text_message(self, message):
        pass

    def on_binary_message(self, buf):
        pass

    def on_ping(self, message):
        self._send(FRAME_PONG, message)

    def on_pong(self, message):
        pass

    def send(self, message, is_binary=False):
        if is_binary:
            self._send(FRAME_BINARY, message)
        else:
            self._send(FRAME_TEXT, message.encode())

    def send_text(self, message):
        self._send(FRAME_TEXT, message.encode())

    def send_binary(self, buf):
        self._send(FRAME_BINARY, buf)

    def ping(self, data):
        self._send(FRAME_PING, data)

    def close(self, code=ST_NORMAL, message=""):
        # RFC 6455: If there is a body, the first two bytes of the body MUST be
        # a 2-byte unsigned integer
        buffer = struct.pack('>H', code) + message.encode()

        self._send(FRAME_CLOSE, buffer)
        self.request.shutdown(socket.SHUT_WR)
        self._is_closing = True


class WebsocketError(Exception):
    pass
