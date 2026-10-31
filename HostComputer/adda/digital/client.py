import struct
import zlib

from fpga_link.protocol import Frame, FrameDecoder, encode_frame
from .protocol import (Kind, Source, State, ErrorCode, INFO, START, IDENTITY, BLOCK, STATUS,
                       COUNTS, BLOCK_SAMPLES, DeviceInfo, CaptureStatus, CaptureResult)


class DigitalError(RuntimeError):
    def __init__(self, message, code=None):
        super().__init__(message)
        self.code = code
        self.partial = b''


class ExchangeTimeout(DigitalError):
    pass


class DigitalClient:
    def __init__(self, exchange):
        self.exchange = exchange
        self.sequence = 0

    def _request(self, kind, payload=b'', retries=0):
        sequence = self.sequence
        self.sequence = (sequence+1) & 255
        packet = encode_frame(Frame(kind, sequence, payload))
        last_error = 'reply absent or frame CRC invalid'
        for _ in range(retries+1):
            try:
                response = self.exchange(packet)
            except OSError as exc:
                last_error = 'transport exchange failed: ' + str(exc)
                continue
            if not isinstance(response, bytes):
                raise DigitalError('exchange reply must be bytes')
            frames = FrameDecoder().feed(response)
            if not frames:
                continue
            if len(frames) != 1 or frames[0].sequence != sequence:
                raise DigitalError('unexpected or stale frame sequence')
            reply = frames[0]
            if reply.kind == 0xe0:
                if (len(reply.payload) != 2 or reply.payload[0] != kind
                        or reply.payload[1] not in tuple(ErrorCode)):
                    raise DigitalError('invalid ERROR reply')
                raise DigitalError('digital request rejected: {}'.format(reply.payload[1]), reply.payload[1])
            if reply.kind != kind+1:
                raise DigitalError('unexpected reply type')
            return reply.payload
        raise ExchangeTimeout(last_error + '; command result unconfirmed')

    def info(self):
        payload = self._request(Kind.INFO)
        if len(payload) not in (INFO.size, INFO.size + 4):
            raise DigitalError('invalid sampling INFO size')
        magic, major, minor, session, identity, flags, bits, limit = INFO.unpack(payload[:INFO.size])
        external = (major, minor, flags, len(payload)) == (1, 1, 3, INFO.size + 4)
        legacy = (major, minor, flags, len(payload)) == (1, 0, 1, INFO.size)
        rate = struct.unpack('>I', payload[INFO.size:])[0] if external else 50000000
        if (magic != b'ADDT' or not (external or legacy) or not session
                or bits != 8 or limit != 4096
                or (external and rate not in (10000000, 25000000))
                or (legacy and rate != 50000000)):
            raise DigitalError('unsupported sampling capability contract')
        return DeviceInfo(session, identity, flags, bits, limit, rate)

    def start(self, info, count, source, fixed):
        if (type(count) is not int or count not in COUNTS or type(source) not in (int,Source)
                or source not in tuple(Source) or type(fixed) is not int or not 0 <= fixed <= 255):
            raise DigitalError('invalid capture configuration')
        if source == Source.EXTERNAL_ADC and (info.capabilities != 3 or fixed != 0):
            raise DigitalError('external ADC capability absent or invalid fixed code')
        payload = self._request(Kind.CAPTURE, START.pack(count,source,fixed))
        if len(payload) != IDENTITY.size:
            raise DigitalError('invalid capture acknowledgement')
        session, identity = IDENTITY.unpack(payload)
        if session != info.session or identity <= info.capture_id:
            raise DigitalError('capture identity is stale or inconsistent')
        return session, identity

    def _decode_status(self, payload, session, identity):
        if len(payload) != STATUS.size:
            raise DigitalError('invalid status size')
        result = CaptureStatus(*STATUS.unpack(payload))
        if (result.session,result.capture_id) != (session,identity):
            raise DigitalError('status identity mismatch')
        if (result.state not in (State.CAPTURING,State.READY,State.CANCELLED)
                or result.planned not in COUNTS or not 0 <= result.actual <= result.planned
                or result.source not in tuple(Source)
                or (result.state == State.READY and result.actual != result.planned)):
            raise DigitalError('invalid capture status values')
        return result

    def status(self, session, identity):
        return self._decode_status(self._request(Kind.STATUS, IDENTITY.pack(session,identity)),session,identity)

    def cancel(self, session, identity):
        return self._decode_status(self._request(Kind.CANCEL, IDENTITY.pack(session,identity)),session,identity)

    def release(self, session, identity):
        payload = IDENTITY.pack(session,identity)
        if self._request(Kind.RELEASE,payload) != payload:
            raise DigitalError('release identity mismatch')

    def read_block(self, session, identity, offset, count):
        prefix = BLOCK.pack(session,identity,offset,count)
        payload = self._request(Kind.READ,prefix,retries=1)
        if len(payload) != BLOCK.size+2*count or payload[:BLOCK.size] != prefix:
            raise DigitalError('read identity/offset/count mismatch')
        raw = payload[BLOCK.size:]
        if any(raw[1::2]):
            raise DigitalError('8-bit source has nonzero upper bits')
        return raw

    def capture_read(self, count, source, fixed=0, cancel=None, progress=None):
        cancelled = lambda: cancel is not None and cancel.is_set()
        if cancelled():
            return CaptureResult('cancelled',count,b'')
        info = self.info()
        session, identity = self.start(info,count,source,fixed)
        status = None
        for _ in range(64):
            if cancelled():
                self.cancel(session,identity)
                return CaptureResult('cancelled',count,b'',session,identity,source=source,sample_rate=info.sample_rate)
            status = self.status(session,identity)
            if (status.planned,status.source,status.fixed) != (count,source,fixed):
                raise DigitalError('latched acquisition configuration mismatch')
            if status.state != State.CAPTURING:
                break
        if status.state != State.READY:
            raise DigitalError('capture cancelled remotely or polling limit reached')
        raw = bytearray()
        try:
            while len(raw)//2 < count:
                if cancelled():
                    return CaptureResult('cancelled',count,bytes(raw),session,identity,source=source,sample_rate=info.sample_rate)
                offset = len(raw)//2
                raw.extend(self.read_block(session,identity,offset,min(BLOCK_SAMPLES,count-offset)))
                if progress:
                    progress(len(raw)//2)
            if cancelled():
                return CaptureResult('cancelled',count,bytes(raw),session,identity,source=source,sample_rate=info.sample_rate)
            final = self.status(session,identity)
            checksum = zlib.crc32(raw)
            if final != status or checksum != status.crc32:
                raise DigitalError('whole capture CRC32 or frozen metadata mismatch')
        except DigitalError as exc:
            exc.partial = bytes(raw)
            exc.session = session
            exc.capture_id = identity
            exc.source = source
            exc.sample_rate = info.sample_rate
            raise
        return CaptureResult('complete',count,bytes(raw),session,identity,checksum,True,source,info.sample_rate)
