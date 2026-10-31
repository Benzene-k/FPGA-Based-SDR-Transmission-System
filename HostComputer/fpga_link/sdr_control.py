import argparse
from dataclasses import dataclass
import struct
import threading
import time
from .message import encode_text
from .serial_client import SerialClient,LinkError

@dataclass(frozen=True)
class SdrStatus:
    version:int;flags:int;session:int;generation:int;sequence:int;length:int;loaded:int;tx_error:int;rx_error:int
    @property
    def tx_busy(self):return bool(self.flags&1)
    @property
    def packet_ready(self):return bool(self.flags&4)

@dataclass(frozen=True)
class SdrProfile:
    version:int;rf_profile:int;center_hz:int;bandwidth_hz:int;rf_rate:int;base_rate:int;points:int;minimum_peak:int;minimum_margin:int

@dataclass(frozen=True)
class ReceivedMessage:
    session:int;generation:int;sequence:int;payload:bytes
    def text(self):return self.payload.decode('utf8',errors='strict')

@dataclass(frozen=True)
class BootSession:
    bound:bool
    session:int

class SdrMessages:
    def __init__(self,client,timeout=.5):
        self.client=client;self.timeout=timeout;self._lock=threading.RLock()
    def _request(self,kind,payload=b''):
        return self.client.request_frame(kind,kind|0x80,timeout=self.timeout,payload=payload).payload
    def _empty(self,kind,payload=b''):
        if self._request(kind,payload)!=b'':raise LinkError('Invalid SDR command acknowledgement')
    def _boot_session(self,payload=b''):
        raw=self._request(0x59,payload)
        if len(raw)!=6:raise LinkError('Invalid boot-session reply length')
        version,bound,session=struct.unpack('>BBI',raw)
        if version!=1 or bound not in (0,1) or bool(session)!=bool(bound):
            raise LinkError('Invalid boot-session state')
        return BootSession(bool(bound),session)
    def boot_session(self):
        with self._lock:return self._boot_session()
    def bind_boot_session(self,base):
        if type(base)is not int or not 0xad000100<=base<=0xadfffe00 or base&255:
            raise ValueError('Boot session requires a freshly reserved aligned AD block')
        with self._lock:
            result=self._boot_session(struct.pack('>I',base))
            if not result.bound or result.session!=base:raise LinkError('Boot-session readback mismatch')
            return result
    def load(self,payload,sequence=0):
        if not isinstance(payload,bytes) or len(payload)>256:raise ValueError('Payload must be bytes, at most 256 bytes')
        if type(sequence)is not int or not 0<=sequence<=65535:raise ValueError('Sequence must be an unsigned 16-bit integer')
        with self._lock:
            self._empty(0x50,struct.pack('>HH',sequence,len(payload)))
            for offset in range(0,len(payload),128):
                part=payload[offset:offset+128]
                if self._request(0x51,offset.to_bytes(2,'big')+part)!=(offset+len(part)).to_bytes(2,'big'):
                    raise LinkError('SDR upload position mismatch; task not sent')
    def send(self):
        with self._lock:self._empty(0x52)
    def send_text(self,text,sequence=0):
        payload=encode_text(text)
        with self._lock:self.load(payload,sequence);self.send()
        return len(payload)
    def status(self):
        with self._lock:raw=self._request(0x53)
        if len(raw)!=18:raise LinkError('Invalid SDR status length')
        status=SdrStatus(*struct.unpack('>BBIIHHHBB',raw))
        if status.version!=1 or status.length>256 or status.loaded>256:raise LinkError('Unsupported SDR status')
        return status
    def receive(self,status=None):
        with self._lock:
            status=self.status() if status is None else status
            if not isinstance(status,SdrStatus):raise TypeError('Expected SdrStatus')
            if not status.packet_ready:return None
            parts=[]
            for offset in range(0,status.length,128):
                count=min(128,status.length-offset)
                raw=self._request(0x54,struct.pack('>IIHB',status.session,status.generation,offset,count))
                if len(raw)!=14+count:raise LinkError('SDR result block length mismatch')
                identity=struct.unpack('>IIHHH',raw[:14])
                if identity!=(status.session,status.generation,status.sequence,status.length,offset):
                    raise LinkError('SDR result identity changed; no release issued')
                parts.append(raw[14:])
            return ReceivedMessage(status.session,status.generation,status.sequence,b''.join(parts))
    def release(self,message):
        if not isinstance(message,ReceivedMessage):raise TypeError('Expected verified ReceivedMessage')
        with self._lock:self._empty(0x55,struct.pack('>II',message.session,message.generation))
    def abort(self,tx=True,rx=False):
        if type(tx)is not bool or type(rx)is not bool or not(tx or rx):raise ValueError('Select TX and/or RX')
        with self._lock:self._empty(0x56,bytes((int(tx)|int(rx)<<1,)))
    def _profile(self,payload=b''):
        raw=self._request(0x57,payload)
        if len(raw)!=28:raise LinkError('Invalid SDR profile length')
        profile=SdrProfile(*struct.unpack('>BBIIIIHII',raw))
        if profile.version!=1:raise LinkError('Unsupported SDR profile')
        return profile
    def profile(self):
        with self._lock:return self._profile()
    def set_thresholds(self,minimum_peak,minimum_margin):
        for value in (minimum_peak,minimum_margin):
            if type(value)is not int or not 0<=value<=0xffffffff:raise ValueError('Thresholds must be unsigned 32-bit integers')
        with self._lock:
            profile=self._profile(struct.pack('>II',minimum_peak,minimum_margin))
            if (profile.minimum_peak,profile.minimum_margin)!=(minimum_peak,minimum_margin):raise LinkError('SDR threshold readback mismatch')
            return profile
    def loopback(self):
        with self._lock:
            raw=self._request(0x58)
            if len(raw)!=2 or raw[0]!=1 or raw[1] not in (0,1):raise LinkError('Invalid loopback mode reply')
            return bool(raw[1])
    def set_loopback(self,enabled):
        if type(enabled)is not bool:raise ValueError('Loopback mode must be a boolean')
        with self._lock:
            raw=self._request(0x58,bytes((int(enabled),)))
            if raw!=bytes((1,int(enabled))):raise LinkError('Loopback mode readback mismatch')
            return enabled

def main():
    parser=argparse.ArgumentParser(description='SDR FPGA message control; opens only the explicitly named UART port')
    parser.add_argument('--port',required=True);parser.add_argument('--baud',type=int,default=115200)
    action=parser.add_mutually_exclusive_group()
    action.add_argument('--send');action.add_argument('--receive',action='store_true')
    action.add_argument('--set-thresholds',nargs=2,type=int,metavar=('PEAK','MARGIN'))
    action.add_argument('--abort',choices=['tx','rx','both'])
    action.add_argument('--loopback',choices=['on','off'],help='Explicit internal digital RF test; holds physical DAC at midpoint')
    action.add_argument('--bind-session',metavar='REGISTRY',help='Explicit Flash boot handshake using the single current session ledger')
    parser.add_argument('--sequence',type=int,default=0);parser.add_argument('--wait',type=float,default=5)
    parser.add_argument('--release',action='store_true')
    args=parser.parse_args()
    if args.release and not args.receive:parser.error('--release requires --receive')
    if args.wait<=0:parser.error('--wait must be positive')
    if args.send is not None:encode_text(args.send)
    client=SerialClient()
    try:
        client.open(args.port,args.baud);radio=SdrMessages(client)
        if args.bind_session:
            from .flash_session import bind_fresh_session
            print(bind_fresh_session(radio,args.bind_session))
            return
        print(radio.profile());status=radio.status();print(status)
        if args.send is not None:
            if status.session==0 or status.session&0xffffff00==0xadffff00:
                raise LinkError('Unreserved candidate session; transmission refused')
            count=radio.send_text(args.send,args.sequence)
            print('FPGA已接受发送任务：{}字节；接收结果需在接收板读取。'.format(count))
        elif args.receive:
            deadline=time.monotonic()+args.wait
            while not status.packet_ready and time.monotonic()<deadline:
                time.sleep(.1);status=radio.status()
            message=radio.receive(status)
            if message is None:raise LinkError('等待接收结果超时')
            print(message.text())
            if args.release:radio.release(message)
        elif args.set_thresholds:print(radio.set_thresholds(*args.set_thresholds))
        elif args.abort:radio.abort(tx=args.abort in ('tx','both'),rx=args.abort in ('rx','both'))
        elif args.loopback:print('digital_loopback='+str(radio.set_loopback(args.loopback=='on')))
    finally:client.close()
if __name__=='__main__':main()
