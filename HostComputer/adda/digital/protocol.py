import struct
from dataclasses import dataclass
from enum import IntEnum
from typing import Optional


class Kind(IntEnum):
    INFO=0x40
    INFO_REPLY=0x41
    CAPTURE=0x42
    CAPTURE_REPLY=0x43
    STATUS=0x44
    STATUS_REPLY=0x45
    READ=0x46
    READ_REPLY=0x47
    CANCEL=0x48
    CANCEL_REPLY=0x49
    RELEASE=0x4a
    RELEASE_REPLY=0x4b


class Source(IntEnum):
    RAMP=0
    FIXED=1
    WALKING=2
    EXTERNAL_ADC=3


class State(IntEnum):
    EMPTY=0
    CAPTURING=1
    READY=2
    CANCELLED=3


class ErrorCode(IntEnum):
    ARGUMENT=1
    BUSY=2
    STALE_SESSION=3
    STALE_CAPTURE=4
    NOT_READY=5
    RANGE=6
    UNSUPPORTED=7
    ID_EXHAUSTED=8


INFO = struct.Struct('>4sBBIIIBH')
START = struct.Struct('>HBB')
IDENTITY = struct.Struct('>II')
BLOCK = struct.Struct('>IIHH')
STATUS = struct.Struct('>IIBHHIBB')
COUNTS = (256, 1024, 4096)
BLOCK_SAMPLES = 120


@dataclass(frozen=True)
class DeviceInfo:
    session: int
    capture_id: int
    capabilities: int
    bits: int
    max_count: int
    sample_rate: int = 50000000


@dataclass(frozen=True)
class CaptureStatus:
    session: int
    capture_id: int
    state: int
    planned: int
    actual: int
    crc32: int
    source: int
    fixed: int


@dataclass(frozen=True)
class CaptureResult:
    state: str
    planned: int
    raw: bytes
    session: int = 0
    capture_id: int = 0
    crc32: Optional[int] = None
    verified: bool = False

    source: Optional[int] = None
    sample_rate: Optional[int] = None
