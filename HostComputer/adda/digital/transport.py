from fpga_link.protocol import Frame, FrameDecoder, encode_frame
from fpga_link.serial_client import LinkError, ReplyTimeout, RemoteError
from .client import DigitalError
from .protocol import Kind


class SerialExchange:
    def __init__(self, client, timeout=0.5):
        if not 0 < timeout <= 5:
            raise ValueError('digital timeout must be positive and at most 5 seconds')
        self.client, self.timeout = client, timeout

    def __call__(self, packet):
        frames = FrameDecoder().feed(packet)
        if len(frames) != 1 or encode_frame(frames[0]) != packet:
            raise DigitalError('invalid outgoing digital frame')
        request = frames[0]
        if request.kind not in (Kind.INFO,Kind.CAPTURE,Kind.STATUS,Kind.READ,Kind.CANCEL,Kind.RELEASE):
            raise DigitalError('unsupported digital request kind')
        try:
            response = self.client.request_frame(int(request.kind),int(request.kind)+1,
                                                 timeout=self.timeout,payload=request.payload)
        except ReplyTimeout:
            return b''
        except RemoteError as exc:
            response = exc.frame
            if response is None:
                raise DigitalError(str(exc)) from exc
        except LinkError as exc:
            raise DigitalError(str(exc)) from exc
        return encode_frame(Frame(response.kind,request.sequence,response.payload))
