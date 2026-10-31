from .flash_session import bind_fresh_session
from .message import encode_text
from .sdr_control import SdrMessages
from .serial_client import LinkError
from adda.digital.client import DigitalClient, DigitalError
from adda.digital.transport import SerialExchange


class RfStateError(ValueError):
    pass


class RfService:
    def __init__(self, client):
        self.radio = SdrMessages(client)
        self.capture = DigitalClient(SerialExchange(client))
        self.session = None

    def prepare(self, registry):
        self.session = None
        boot = bind_fresh_session(self.radio, registry)
        profile = self.radio.profile()
        if (profile.rf_profile, profile.center_hz, profile.bandwidth_hz,
                profile.rf_rate, profile.base_rate, profile.points) != (
                1, 7000000, 1000000, 25000000, 2500000, 4096):
            raise RfStateError('需要当前外部 ADC RF 配置；板内诊断回环不可当作天线接收。')
        if self.radio.loopback():
            raise RfStateError('板内诊断回环已开启，请先按诊断流程关闭。')
        info = self.capture.info()
        if info.session != boot.session or info.sample_rate != profile.rf_rate:
            raise LinkError('RF 与 ADC 身份或采样率不一致')
        self.session = boot.session
        status = self.checked_status()
        return dict(session=boot.session, profile=profile, status=status)

    def checked_status(self):
        if self.session is None:
            raise RfStateError('请先检查并绑定 RF 会话。')
        status = self.radio.status()
        if status.session != self.session:
            self.session = None
            raise RfStateError('板卡会话已变化，自动任务已停止；请重新检查并绑定。')
        if status.flags & 64:
            raise RfStateError('设备处于板内诊断回环，不能标记为外部接收。')
        if status.flags & 16:
            raise RfStateError('FPGA 报告当前流故障；停止自动任务，请检查设备状态。')
        return status

    def send_text(self, text, sequence):
        payload = encode_text(text)
        if type(sequence) is not int or not 0 <= sequence <= 65535:
            raise ValueError('消息序号须为 0～65535。')
        status = self.checked_status()
        if status.tx_busy:
            raise RfStateError('FPGA 正在发送，请等待完成；没有重新发送。')
        self.radio.load(payload, sequence)
        self.radio.send()
        return dict(bytes=len(payload), sequence=sequence)

    def poll(self, waveform, count, cancel):
        if type(waveform) is not bool or type(count) is not int or count not in (256, 1024, 4096):
            raise ValueError('采集点数或波形开关无效。')
        result = dict(message=None, capture=None, status=None)
        if cancel.is_set():
            return result
        status = self.checked_status()
        result['status'] = status
        if status.packet_ready:
            message = self.radio.receive(status)
            result['message'] = message
            self.partial_result = dict(result)
            self.radio.release(message)
        if waveform and not cancel.is_set():
            info = self.capture.info()
            if info.session != self.session or info.sample_rate != 25000000:
                raise RfStateError('ADC 会话或采样率已变化，请重新检查。')
            if info.capture_id:
                try:
                    self.capture.status(info.session, info.capture_id)
                except DigitalError as exc:
                    if exc.code != 5:
                        raise
                else:
                    raise RfStateError('板上存在未释放的采集，请先在 AD/DA 页检查并释放缓存。')
            capture = self.capture.capture_read(count, 3, cancel=cancel)
            if capture.session:
                result['capture'] = capture if capture.verified else None
                self.partial_result = dict(result)
                self.capture.release(capture.session, capture.capture_id)
        return result

    def execute(self, operation, payload):
        self.partial_result = None
        if operation == 'RF_PREPARE':
            return self.prepare(payload['registry'])
        if operation == 'RF_SEND':
            return self.send_text(payload['text'], payload['sequence'])
        if operation == 'RF_POLL':
            return self.poll(payload['waveform'], payload['count'], payload['cancel'])
        if operation == 'RF_STATUS':
            return dict(status=self.checked_status())
        if operation == 'RF_ABORT_TX':
            self.checked_status()
            self.radio.abort(tx=True, rx=False)
            return dict(status=self.checked_status())
        raise ValueError('未知 RF 任务。')
