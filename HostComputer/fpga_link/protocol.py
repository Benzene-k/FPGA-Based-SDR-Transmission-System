from dataclasses import dataclass
from enum import IntEnum
import binascii
import time

HEADER = b"\xaa\x55"
MAX_PAYLOAD = 256


class Message(IntEnum):
    PING = 0x01
    PONG = 0x02
    START = 0x12
    STOP = 0x13
    RESET = 0x14
    ECHO = 0x20
    ECHO_REPLY = 0x21
    CONFIG_GET = 0x30
    CONFIG_REPLY = 0x31
    CONFIG_SET = 0x32
    ACK = 0x80
    ERROR = 0xE0


@dataclass(frozen=True)
class Frame:
    kind: int
    sequence: int
    payload: bytes = b""


def crc16(data: bytes) -> int:
    return binascii.crc_hqx(data, 0xFFFF)


def encode_frame(frame: Frame) -> bytes:
    if not 0 <= frame.kind <= 255 or not 0 <= frame.sequence <= 255:
        raise ValueError("TYPE and SEQ must be unsigned bytes")
    if not isinstance(frame.payload, bytes) or len(frame.payload) > MAX_PAYLOAD:
        raise ValueError("Payload must be bytes, at most 256 bytes")
    body = bytes((frame.kind, frame.sequence)) + len(frame.payload).to_bytes(2, "big") + frame.payload
    return HEADER + body + crc16(body).to_bytes(2, "big")


class FrameDecoder:
    def __init__(self, frame_timeout=0.1):
        if frame_timeout <= 0:
            raise ValueError("frame_timeout must be positive")
        self.frame_timeout = frame_timeout
        self._buffer = bytearray()
        self._last_byte_time = None
        self.crc_errors = self.length_errors = self.timeouts = 0

    def feed(self, data, now=None):
        now = time.monotonic() if now is None else now
        if self._buffer and self._last_byte_time is not None and now - self._last_byte_time > self.frame_timeout:
            self._buffer.clear()
            self.timeouts += 1
        if data:
            self._last_byte_time = now
            self._buffer.extend(data)
        frames = []
        while self._buffer:
            start = self._buffer.find(HEADER)
            if start < 0:
                self._buffer[:] = b"\xaa" if self._buffer[-1] == 0xAA else b""
                break
            del self._buffer[:start]
            if len(self._buffer) < 6:
                break
            length = int.from_bytes(self._buffer[4:6], "big")
            if length > MAX_PAYLOAD:
                self.length_errors += 1
                del self._buffer[0]
                continue
            total = length + 8
            if len(self._buffer) < total:
                break
            body = bytes(self._buffer[2:total - 2])
            if crc16(body) != int.from_bytes(self._buffer[total - 2:total], "big"):
                self.crc_errors += 1
                del self._buffer[0]
                continue
            frames.append(Frame(body[0], body[1], body[4:]))
            del self._buffer[:total]
        return frames
