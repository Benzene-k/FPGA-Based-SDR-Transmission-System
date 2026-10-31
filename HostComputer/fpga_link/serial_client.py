import logging
import queue
import threading
import time
from dataclasses import dataclass

from .configuration import CommConfig
from .protocol import Frame, FrameDecoder, Message, MAX_PAYLOAD, encode_frame

log = logging.getLogger(__name__)


class LinkError(Exception):
    pass


class ReplyTimeout(LinkError):
    pass


class RemoteError(LinkError):
    def __init__(self, message, frame=None):
        super().__init__(message)
        self.frame = frame


@dataclass(frozen=True)
class DeviceInfo:
    major: int
    minor: int
    flags: int
    requested_running: bool

    @property
    def comm_only(self):
        return bool(self.flags & 1)

    @property
    def supports_echo(self):
        return bool(self.flags & 2)

    @property
    def supports_config(self):
        return bool(self.flags & 4)


class SerialClient:
    def __init__(self, serial_factory=None):
        if serial_factory is None:
            import serial
            serial_factory = serial.serial_for_url
        self._factory = serial_factory
        self._port = self._reader = None
        self._stop = threading.Event()
        self._replies = queue.Queue(maxsize=256)
        self._commands = threading.Lock()
        self._sequence = 0
        self._reader_error = None
        self.decoder = FrameDecoder()

    def open(self, port, baudrate=115200):
        self.close()
        connection = self._factory(port, baudrate=baudrate, timeout=0.05, write_timeout=0.5)
        self.decoder = FrameDecoder()
        self._replies = queue.Queue(maxsize=256)
        self._stop = threading.Event()
        self._reader_error = None
        self._sequence = 0
        self._port = connection
        self._reader = threading.Thread(target=self._read_loop, args=(connection,), daemon=True)
        self._reader.start()

    def close(self):
        connection, self._port = self._port, None
        self._stop.set()
        self._offer(LinkError("serial connection closed"))
        try:
            if connection is not None:
                connection.close()
        finally:
            if self._reader is not None:
                self._reader.join(timeout=1)
                if self._reader.is_alive():
                    raise LinkError("serial reader did not stop; reconnect refused")
            self._reader = None

    def _offer(self, item):
        try:
            self._replies.put_nowait(item)
        except queue.Full:
            self._reader_error = LinkError("reply queue overflow")
            self._stop.set()

    def _read_loop(self, connection):
        try:
            while not self._stop.is_set():
                data = connection.read(512)
                if self._stop.is_set():
                    return
                if data:
                    log.info("RX %s", data.hex(" "))
                for frame in self.decoder.feed(data):
                    self._offer(frame)
        except Exception as exc:
            if not self._stop.is_set():
                self._reader_error = LinkError("serial read failed: {}".format(exc))
                self._stop.set()
                self._offer(self._reader_error)

    def _request(self, kind, reply_kind, timeout, retries=0, payload=b""):
        if timeout <= 0 or retries < 0:
            raise ValueError("timeout must be positive and retries nonnegative")
        with self._commands:
            connection = self._port
            if connection is None or self._stop.is_set():
                raise self._reader_error or LinkError("serial port is not connected")
            while True:
                try:
                    self._replies.get_nowait()
                except queue.Empty:
                    break
            sequence = self._sequence
            self._sequence = (sequence + 1) & 255
            packet = encode_frame(Frame(kind, sequence, payload))
            for attempt in range(retries + 1):
                if self._stop.is_set():
                    raise self._reader_error or LinkError("serial connection closed")
                try:
                    log.info("TX %s", packet.hex(" "))
                    if connection.write(packet) != len(packet):
                        raise LinkError("partial serial write; command result unknown")
                except LinkError:
                    raise
                except Exception as exc:
                    raise LinkError("serial write failed: {}".format(exc)) from exc
                deadline = time.monotonic() + timeout
                while True:
                    if self._stop.is_set():
                        raise self._reader_error or LinkError("serial connection closed")
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    try:
                        response = self._replies.get(timeout=remaining)
                    except queue.Empty:
                        break
                    if isinstance(response, Exception):
                        raise response
                    if response.sequence != sequence:
                        continue
                    extension_error = (0x50 <= kind <= 0x59 and response.kind == 0xdf
                                       and len(response.payload) == 2 and response.payload[0] == kind)
                    if response.kind == Message.ERROR or extension_error:
                        raise RemoteError("FPGA ERROR: {}".format(response.payload.hex(" ")), response)
                    if response.kind == reply_kind:
                        return response
            label = Message(kind).name if kind in Message._value2member_map_ else '0x{:02X}'.format(kind)
            raise ReplyTimeout("{} reply timed out; command result unknown".format(label))

    def request_frame(self, kind, reply_kind, timeout=0.5, payload=b''):
        if (type(kind) is not int or type(reply_kind) is not int
                or not 0 <= kind <= 255 or not 0 <= reply_kind <= 255):
            raise ValueError('request and reply kinds must be byte integers')
        if not isinstance(payload, bytes) or len(payload) > MAX_PAYLOAD:
            raise ValueError('payload must be bytes, at most 256 bytes')
        return self._request(kind, reply_kind, timeout, payload=payload)

    def ping(self, timeout=0.5, retries=2):
        response = self._request(Message.PING, Message.PONG, timeout, retries)
        if len(response.payload) != 4 or response.payload[0] != 1 or response.payload[3] not in (0, 1):
            raise LinkError("invalid PONG or unsupported protocol version")
        return DeviceInfo(*response.payload[:3], bool(response.payload[3]))

    def control(self, kind, timeout=0.5):
        if kind not in (Message.START, Message.STOP, Message.RESET):
            raise ValueError("control must be START, STOP or RESET")
        response = self._request(kind, Message.ACK, timeout)
        if len(response.payload) != 3 or response.payload[:2] != bytes((kind, 0)) or response.payload[2] not in (0, 1):
            raise LinkError("invalid command ACK")
        return bool(response.payload[2])

    def echo(self, payload, timeout=0.5):
        if not isinstance(payload, bytes) or len(payload) > MAX_PAYLOAD:
            raise ValueError("Echo payload must be bytes, at most 256 bytes")
        response = self._request(Message.ECHO, Message.ECHO_REPLY, timeout, payload=payload)
        if response.payload != payload:
            raise LinkError("echo payload mismatch: sent {} bytes, received {} bytes".format(
                len(payload), len(response.payload)))
        return response.payload

    def get_config(self, timeout=0.5):
        response = self._request(Message.CONFIG_GET, Message.CONFIG_REPLY, timeout)
        try:
            return CommConfig.decode(response.payload)
        except ValueError as exc:
            raise LinkError('Invalid configuration reply: ' + str(exc)) from exc

    def set_config(self, config, timeout=0.5):
        if not isinstance(config, CommConfig):
            raise ValueError('Expected CommConfig')
        payload = config.encode()
        response = self._request(Message.CONFIG_SET, Message.CONFIG_REPLY, timeout, payload=payload)
        try:
            stored = CommConfig.decode(response.payload)
        except ValueError as exc:
            raise LinkError('Invalid configuration reply: ' + str(exc)) from exc
        if stored != config:
            raise LinkError('Configuration write reply mismatch; stored result unknown')
        return stored
