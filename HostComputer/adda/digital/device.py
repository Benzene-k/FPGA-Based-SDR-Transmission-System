import struct
import zlib

from fpga_link.protocol import Frame, FrameDecoder, encode_frame
from .protocol import Kind, Source, State, ErrorCode, INFO, START, IDENTITY, BLOCK, STATUS, COUNTS, BLOCK_SAMPLES


class Rejected(Exception):
    def __init__(self, code):
        self.code = code


class DigitalDevice:
    def __init__(self, session=1, step=256, samples=None, external_samples=None):
        if type(session) is not int or not 1 <= session <= 0xffffffff:
            raise ValueError('session must be a nonzero u32')
        if type(step) is not int or not 0 <= step <= 4096:
            raise ValueError('step must be 0..4096')
        if samples is not None and (not isinstance(samples, bytes) or len(samples) != 8192
                                    or any(samples[1::2])):
            raise ValueError('RTL sample fixture must contain 4096 u16 little-endian 8-bit codes')
        if external_samples is not None and (not isinstance(external_samples, bytes) or len(external_samples) != 8192 or any(external_samples[1::2])):
            raise ValueError('external fixture must contain 4096 unsigned 8-bit u16 samples')
        self.external_samples = external_samples
        self.session, self.step, self.samples = session, step, samples
        self.decoder = FrameDecoder()
        self.capture_id = 0
        self.state = State.EMPTY
        self.raw = bytearray()
        self.planned = self.source = self.fixed = 0

    def reset(self):
        if self.session == 0xffffffff:
            raise ValueError('session exhausted; cannot reuse old identities')
        self.session += 1
        self.capture_id = 0
        self.state = State.EMPTY
        self.raw.clear()
        self.decoder = FrameDecoder()

    def advance(self, count):
        if self.state != State.CAPTURING:
            return
        first = len(self.raw)//2
        end = min(first+count, self.planned)
        for index in range(first, end):
            value = (index & 255 if self.source == Source.RAMP else self.fixed
                     if self.source == Source.FIXED else 1 << (index & 7))
            if self.samples is not None and self.source == Source.RAMP:
                value = self.samples[index*2]
            if self.source == Source.EXTERNAL_ADC:
                value = self.external_samples[index*2]
            self.raw.extend((value, 0))
        if end == self.planned:
            self.state = State.READY

    def _identity(self, session, capture_id):
        if session != self.session:
            raise Rejected(ErrorCode.STALE_SESSION)
        if not capture_id or capture_id != self.capture_id:
            raise Rejected(ErrorCode.STALE_CAPTURE)
        if self.state == State.EMPTY:
            raise Rejected(ErrorCode.NOT_READY)

    def _status(self):
        return STATUS.pack(self.session, self.capture_id, self.state, self.planned,
                           len(self.raw)//2, zlib.crc32(self.raw), self.source, self.fixed)

    def exchange(self, packet):
        frames = self.decoder.feed(packet)
        if len(frames) != 1:
            return b''
        request = frames[0]
        self.advance(self.step)
        try:
            kind, payload = self._handle(request.kind, request.payload)
        except Rejected as exc:
            kind, payload = 0xe0, bytes((request.kind, int(exc.code)))
        except (struct.error, ValueError):
            kind, payload = 0xe0, bytes((request.kind, ErrorCode.ARGUMENT))
        return encode_frame(Frame(kind, request.sequence, payload))

    def _handle(self, kind, payload):
        if kind == Kind.INFO:
            if payload:
                raise Rejected(ErrorCode.ARGUMENT)
            external = self.external_samples is not None
            return Kind.INFO_REPLY, INFO.pack(b'ADDT',1,int(external),self.session,self.capture_id,3 if external else 1,8,4096) + (struct.pack('>I',10000000) if external else b'')
        if kind == Kind.CAPTURE:
            planned, source, fixed = START.unpack(payload)
            if (planned not in COUNTS or source not in tuple(Source)
                    or (source == Source.EXTERNAL_ADC and (self.external_samples is None or fixed != 0))):
                raise Rejected(ErrorCode.ARGUMENT)
            if self.state == State.CAPTURING:
                raise Rejected(ErrorCode.BUSY)
            if self.state != State.EMPTY:
                raise Rejected(ErrorCode.NOT_READY)
            if self.capture_id == 0xffffffff:
                raise Rejected(ErrorCode.ID_EXHAUSTED)
            self.capture_id += 1
            self.planned, self.source, self.fixed = planned, source, fixed
            self.raw.clear()
            self.state = State.CAPTURING
            return Kind.CAPTURE_REPLY, IDENTITY.pack(self.session,self.capture_id)
        if kind not in (Kind.STATUS, Kind.READ, Kind.CANCEL, Kind.RELEASE):
            raise Rejected(ErrorCode.UNSUPPORTED)
        if kind == Kind.READ:
            session, identity, offset, count = BLOCK.unpack(payload)
        else:
            session, identity = IDENTITY.unpack(payload)
        self._identity(session, identity)
        if kind == Kind.STATUS:
            return Kind.STATUS_REPLY, self._status()
        if kind == Kind.CANCEL:
            if self.state == State.CAPTURING:
                self.state = State.CANCELLED
            return Kind.CANCEL_REPLY, self._status()
        if self.state == State.CAPTURING:
            raise Rejected(ErrorCode.BUSY)
        if kind == Kind.RELEASE:
            self.state = State.EMPTY
            self.raw.clear()
            return Kind.RELEASE_REPLY, IDENTITY.pack(session,identity)
        if not 1 <= count <= BLOCK_SAMPLES or offset+count > len(self.raw)//2:
            raise Rejected(ErrorCode.RANGE)
        return Kind.READ_REPLY, BLOCK.pack(session,identity,offset,count) + bytes(self.raw[2*offset:2*(offset+count)])
