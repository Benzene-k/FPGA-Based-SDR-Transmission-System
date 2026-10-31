from threading import Event
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QWidget, QGroupBox, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox, QSpinBox
from .models import CaptureConfig, WaveConfig, make_digital_snapshot
from .digital.protocol import CaptureResult


class DigitalCaptureBox(QGroupBox):
    changed = pyqtSignal()
    message = pyqtSignal(str)
    snapshot_ready = pyqtSignal(object)
    partial_ready = pyqtSignal(object)
    progress = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__('FPGA 板内数字源 · 8 bit · 不读取真实 ADC', parent)
        self.adc_mode = False
        self.link = None
        self.info = self.identity = None
        self.busy = self.closing = False
        self.state = {}
        self._operation = None
        self._cancel = Event()
        self._config = None
        layout = QVBoxLayout(self)
        self.parameters = QWidget()
        parameter_layout = QVBoxLayout(self.parameters)
        parameter_layout.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        self.count_combo = QComboBox()
        for n in (256, 1024, 4096): self.count_combo.addItem(str(n), n)
        self.count_combo.setCurrentIndex(2)
        self.wave_combo = QComboBox()
        for text, value in [('递增码', 0), ('固定码', 1), ('Walking 单比特码', 2)]:
            self.wave_combo.addItem(text, value)
        self.fixed = QSpinBox()
        self.fixed.setRange(0, 255)
        self.fixed.setValue(173)
        self.fixed.setSuffix(' code')
        self.pattern_labels = []
        for text, widget in [('点数', self.count_combo), ('码型', self.wave_combo), ('固定码', self.fixed)]:
            label = QLabel(text)
            if widget is not self.count_combo:
                self.pattern_labels.append(label)
            row.addWidget(label)
            row.addWidget(widget)
        parameter_layout.addLayout(row)
        self.note = note = QLabel('时间/频率轴按当前测试镜像标称 50 MSa/s 计算，非实测；默认查看样本序号。\n采集完成后缓存保持冻结，释放后才能再次采集；不启用外部 ADC/DAC。')
        note.setWordWrap(True)
        parameter_layout.addWidget(note)
        layout.addWidget(self.parameters)
        actions = QHBoxLayout()
        self.probe_button = QPushButton('检查数字源能力 / 缓存状态')
        self.release_button = QPushButton('释放板上缓存')
        self.probe_button.clicked.connect(self.probe)
        self.release_button.clicked.connect(self.release)
        actions.addWidget(self.probe_button)
        actions.addWidget(self.release_button)
        layout.addLayout(actions)
        self.status_label = QLabel('未检查能力；仅 PING 在线不能确认支持数字采样。')
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        self.wave_combo.currentIndexChanged.connect(self.update_controls)
        self.update_controls()

    def set_adc_mode(self, enabled):
        self.adc_mode = bool(enabled)
        for widget in self.pattern_labels + [self.wave_combo, self.fixed]:
            widget.setVisible(not enabled)
        self.setTitle('真实 ADC · ATK-MO8008 V3.3 · 单路 8 bit' if enabled else 'FPGA 板内数字源 · 8 bit · 不读取真实 ADC')
        self.note.setText('采样率由镜像声明，非实测。采集后缓存冻结，释放后才能再次采集。\n真实 ADC 未做电压校准；OTR 未统计；RF 控制请使用文本收发页。' if enabled else
                          '时间/频率轴按镜像标称采样率计算，非实测；默认查看样本序号。\n板内数字源不读取真实 ADC；采集后需显式释放缓存。')
        self.update_controls()

    def bind_link(self, link):
        if self.link is not None:
            raise ValueError('数字源控件只能绑定一个串口调度器。')
        self.link = link
        link.digital_completed.connect(self._completed)
        link.digital_failed.connect(self._failed)
        link.digital_progress.connect(lambda report: self.progress.emit(report['received']) if self.busy else None)
        link.link_state_changed.connect(self.set_link_state)
        self.set_link_state(link.link_state())

    def set_link_state(self, state):
        if not state.get('connected'):
            self.info = self.identity = None
            self.status_label.setText('未连接；请前往 FPGA 通信连接后检查数字源能力。')
        self.state = dict(state)
        self.update_controls()

    @property
    def can_capture(self):
        return (self._available() and self.info is not None and self.identity is None
                and (not self.adc_mode or self.info.capabilities == 3))

    @property
    def capturing(self):
        return self.busy and self._operation == 'DIGITAL_CAPTURE'

    def _available(self):
        return bool(self.link and self.state.get('connected') and self.state.get('available', not self.state.get('busy'))
                    and not self.state.get('sending_paused') and not self.busy and not self.closing)

    def update_controls(self, *args):
        self.probe_button.setEnabled(self._available())
        self.release_button.setEnabled(self._available() and self.identity is not None)
        for widget in (self.count_combo, self.wave_combo): widget.setEnabled(not self.busy and not self.closing)
        self.fixed.setEnabled(not self.busy and not self.closing and self.wave_combo.currentData() == 1 and not self.adc_mode)
        self.wave_combo.setEnabled(not self.busy and not self.closing and not self.adc_mode)
        self.changed.emit()

    def _submit(self, operation, payload):
        if not self._available():
            return False
        self.busy = True
        self._operation = operation
        self.update_controls()
        if not self.link.submit_digital(operation, payload):
            self.busy = False
            self._operation = None
            self.message.emit('当前串口忙碌、已暂停或未连接，请稍后重试。')
            self.update_controls()
            return False
        return True

    def probe(self):
        if self._available():
            self.info = self.identity = None
            self.status_label.setText('正在检查 D0 数字源能力…')
            self._submit('DIGITAL_INFO', {})

    def capture(self):
        if not self.can_capture: return False
        source = 3 if self.adc_mode else self.wave_combo.currentData()
        fixed = self.fixed.value() if source == 1 else 0
        self._config = CaptureConfig(self.count_combo.currentData(), self.info.sample_rate,
                                   WaveConfig(('ramp', 'fixed', 'walking', 'external_adc')[source], amplitude=0, offset=fixed))
        self._cancel = Event()
        self.status_label.setText('正在采集、读取并校验；旧快照保留。')
        return self._submit('DIGITAL_CAPTURE', dict(count=self._config.count, source=source, fixed=fixed, cancel=self._cancel))

    def cancel(self):
        self._cancel.set()

    def release(self):
        if self.identity is not None:
            self._submit('DIGITAL_RELEASE', dict(zip(('session', 'capture_id'), self.identity)))

    def _completed(self, operation, result):
        if self.closing or operation != self._operation: return
        self.busy = False
        self._operation = None
        if operation == 'DIGITAL_INFO':
            self.info = result
            self.status_label.setText('能力已确认 · 会话 {:08X} · 标称 {} MSa/s（非实测） · 真实 ADC {}。'.format(result.session, result.sample_rate / 1e6, '可用' if result.capabilities == 3 else '不支持'))
            if result.capture_id:
                self.identity = (result.session, result.capture_id)
                self._submit('DIGITAL_STATUS', dict(session=result.session, capture_id=result.capture_id))
            else:
                self.message.emit(self.status_label.text())
        elif operation == 'DIGITAL_STATUS':
            self.status_label.setText('会话 {:08X} · 采集 {} · 板上状态 {} · {} / {} 点；缓存需显式释放。'.format(
                result.session, result.capture_id, {1: '采集中', 2: '冻结就绪', 3: '已取消'}[result.state], result.actual, result.planned))
            self.message.emit(self.status_label.text())
        elif operation == 'DIGITAL_RELEASE':
            self.identity = None
            self.status_label.setText('板上缓存已释放；电脑中的冻结快照仍可查看、导出。')
            self.message.emit(self.status_label.text())
        elif operation == 'DIGITAL_CAPTURE':
            if result.session and result.capture_id:
                self.identity = (result.session, result.capture_id)
            if result.raw:
                try:
                    snapshot = make_digital_snapshot(self._config, result)
                    (self.snapshot_ready if result.state == 'complete' else self.partial_ready).emit(snapshot)
                except ValueError as exc:
                    self.message.emit(str(exc))
                    self.update_controls()
                    return
            detail = '采集完成 · 整段 CRC32 通过' if result.verified else '读取已取消 · 未通过整段校验'
            self.status_label.setText('{} · {} / {} 点 · 会话 {:08X} / 采集 {}\n标称 {} MSa/s（非实测）；缓存冻结 · {}。'.format(
                detail, len(result.raw) // 2, result.planned, result.session, result.capture_id, self._config.sample_rate/1e6, '真实 ADC 原始码' if self.adc_mode else '板内数字源，非真实 ADC'))
            self.message.emit(detail + '；下次采集前请点击“释放板上缓存”。')
        self.update_controls()

    def _failed(self, report):
        if self.closing or report['operation'] != self._operation: return
        operation = self._operation
        self._operation = None
        self.busy = False
        if operation == 'DIGITAL_CAPTURE' and report['partial'] and report.get('session') and report.get('capture_id'):
            result = CaptureResult('cancelled', self._config.count, report['partial'],
                                   report['session'], report['capture_id'], source=3 if self.adc_mode else self.wave_combo.currentData(), sample_rate=int(self._config.sample_rate))
            try:
                self.partial_ready.emit(make_digital_snapshot(self._config, result))
            except ValueError as exc:
                self.message.emit('部分数据无法发布：' + str(exc))
        if operation == 'DIGITAL_STATUS' and report['code'] == 5:
            self.identity = None
            self.status_label.setText('数字源能力已确认；板上无冻结缓存，可以采集。')
            self.message.emit(self.status_label.text())
        else:
            self.status_label.setText('数字源操作未完成：' + report['error'])
            self.message.emit(self.status_label.text() + '；当前结果保留，请检查能力 / 缓存状态后重试。')
            if operation != 'DIGITAL_RELEASE' or report['code'] in (3, 4):
                self.info = None
                self.identity = None
        self.update_controls()

    def shutdown(self):
        self.closing = True
        self.cancel()
        self.update_controls()
