from datetime import datetime
from pathlib import Path
from threading import Event

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
                             QPlainTextEdit, QPushButton, QCheckBox, QComboBox,
                             QSplitter, QScrollArea, QFileDialog, QLineEdit)
from adda.models import CaptureConfig, WaveConfig, make_digital_snapshot
from adda.qt_views import SnapshotViews
from adda.export import export_snapshot
from .message import encode_text


class RfPanel(QWidget):
    open_communication = pyqtSignal()
    log_message = pyqtSignal(str)

    def __init__(self, theme, link, parent=None, registry=None):
        super().__init__(parent)
        self.link = link
        self.ready = self.running = self.busy = self.closing = False
        self.tx_pending = False
        self.sequence = self.segment_count = 0
        self._cancel = Event()
        self._last_message = None
        self._link_state = link.link_state()
        self._registry = Path(registry) if registry else (
            Path(__file__).resolve().parents[1]/'ui_validation/digital_board/session_registry.json')
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        splitter = QSplitter(Qt.Horizontal)
        root.addWidget(splitter)
        scroll = QScrollArea()
        scroll.setObjectName('rfScroll')
        scroll.viewport().setObjectName('rfViewport')
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setMinimumWidth(340)
        controls = QWidget()
        controls.setObjectName('rfControls')
        for widget in (scroll, scroll.viewport(), controls):
            widget.setStyleSheet('#' + widget.objectName() + ' { background-color: ' + theme['bg_app'] + '; }')
        left = QVBoxLayout(controls)
        left.setSpacing(12)
        scroll.setWidget(controls)
        splitter.addWidget(scroll)

        connection = QGroupBox('1 · 连接与会话')
        box = QVBoxLayout(connection)
        self.connection_label = QLabel('未连接 · 请先在 FPGA 通信页选择本机串口')
        self.connection_label.setWordWrap(True)
        box.addWidget(self.connection_label)
        row = QHBoxLayout()
        connect = QPushButton('串口连接')
        connect.clicked.connect(self.open_communication)
        self.prepare_button = QPushButton('检查 / 绑定会话')
        self.prepare_button.clicked.connect(self.prepare)
        row.addWidget(connect); row.addWidget(self.prepare_button)
        box.addLayout(row)
        advanced_button = QPushButton('会话账本设置')
        advanced_button.setCheckable(True)
        box.addWidget(advanced_button)
        advanced = QWidget()
        advanced_layout = QVBoxLayout(advanced)
        advanced_layout.setContentsMargins(0, 0, 0, 0)
        warning = QLabel('每台电脑需使用独占区间，不能复制同一范围的账本。')
        warning.setWordWrap(True)
        advanced_layout.addWidget(warning)
        ledger_row = QHBoxLayout()
        self.registry_edit = QLineEdit(str(self._registry))
        self.registry_edit.setAccessibleName('本机专用会话账本路径')
        self.registry_button = QPushButton('选择')
        self.registry_button.clicked.connect(self.choose_registry)
        ledger_row.addWidget(self.registry_edit, 1); ledger_row.addWidget(self.registry_button)
        advanced_layout.addLayout(ledger_row)
        box.addWidget(advanced)
        advanced.hide()
        advanced_button.toggled.connect(advanced.setVisible)
        self.profile_label = QLabel('尚未检查 RF 能力；连接不会自动分配会话或发送。')
        self.profile_label.setWordWrap(True)
        box.addWidget(self.profile_label)
        left.addWidget(connection)

        send_group = QGroupBox('2 · 发送文本')
        box = QVBoxLayout(send_group)
        self.send_edit = QPlainTextEdit()
        self.send_edit.setAccessibleName('待发送文本')
        self.send_edit.setPlaceholderText('输入中文或英文，最多 256 个 UTF-8 字节')
        self.send_edit.setFixedHeight(76)
        box.addWidget(self.send_edit)
        self.byte_label = QLabel()
        box.addWidget(self.byte_label)
        row = QHBoxLayout()
        self.send_button = QPushButton('发送文本')
        self.abort_button = QPushButton('中止 FPGA 发送')
        self.send_button.clicked.connect(self.send_text)
        self.abort_button.clicked.connect(self.abort_tx)
        row.addWidget(self.send_button); row.addWidget(self.abort_button)
        box.addLayout(row)
        self.tx_label = QLabel('尚未发送；发送完成不代表对端收到。')
        self.tx_label.setWordWrap(True)
        box.addWidget(self.tx_label)
        left.addWidget(send_group)

        receive_group = QGroupBox('3 · 持续接收')
        box = QVBoxLayout(receive_group)
        self.start_button = QPushButton('启动接收 / 自动刷新')
        self.stop_button = QPushButton('停止电脑端接收')
        self.start_button.clicked.connect(self.start_receiving)
        self.stop_button.clicked.connect(self.stop_receiving)
        row = QHBoxLayout()
        self.waveform_check = QCheckBox('同时刷新 ADC 波形')
        self.waveform_check.setChecked(True)
        self.count_combo = QComboBox()
        for count in (256, 1024, 4096):
            self.count_combo.addItem('{} 点'.format(count), count)
        self.count_combo.setCurrentIndex(1)
        self.count_combo.setAccessibleName('每段 ADC 采样点数')
        row.addWidget(self.waveform_check); row.addWidget(self.count_combo)
        box.addLayout(row)
        self.status_label = QLabel('未启动 · 波形按段刷新，段间有空隙，不是连续录波。')
        self.status_label.setWordWrap(True)
        box.addWidget(self.status_label)
        self.received_text = QPlainTextEdit()
        self.received_text.setReadOnly(True)
        self.received_text.setAccessibleName('接收到的文本消息和时间')
        self.received_text.setMaximumBlockCount(1000)
        self.received_text.setFixedHeight(72)
        left.addWidget(receive_group)
        left.addStretch()

        view = QWidget()
        right = QVBoxLayout(view)
        right.setContentsMargins(6, 0, 0, 0)
        receive_actions = QHBoxLayout()
        receive_actions.addWidget(self.start_button)
        receive_actions.addWidget(self.stop_button)
        right.addLayout(receive_actions)
        right.addWidget(QLabel('接收文字 · 显示 FPGA 解调后的消息'))
        right.addWidget(self.received_text)
        label = QLabel('外部 ADC 原始码')
        label.setWordWrap(True)
        right.addWidget(label)
        self.views = SnapshotViews(theme)
        for canvas in (self.views.canvas, self.views.fft_canvas):
            canvas.setMinimumHeight(150)
        self.views.window_combo.currentIndexChanged.connect(self._fit_plot_labels)
        self.views.remove_dc.toggled.connect(self._fit_plot_labels)
        self.views.tabs.currentChanged.connect(self._fit_plot_labels)
        right.addWidget(self.views, 1)
        self.export_button = QPushButton('导出当前 ADC 快照')
        self.export_button.clicked.connect(self.export_current)
        right.addWidget(self.export_button)
        splitter.addWidget(view)
        splitter.setStretchFactor(0, 0); splitter.setStretchFactor(1, 1)
        splitter.setSizes([420, 720])

        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._poll)
        self.send_edit.textChanged.connect(self._buttons)
        self.registry_edit.textChanged.connect(self._registry_changed)
        link.link_state_changed.connect(self._state_changed)
        link.rf_completed.connect(self._completed)
        link.rf_failed.connect(self._failed)
        self._buttons()

    def choose_registry(self):
        path, _ = QFileDialog.getOpenFileName(self, '选择本机专用会话账本', str(self._registry), 'JSON (*.json)')
        if path:
            self.registry_edit.setText(path)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'views'):
            compact = self.height() < 600
            self.views.toolbar.setVisible(not compact)
            self.views.fft_toolbar.setVisible(not compact)
            self._fit_plot_labels()

    def _fit_plot_labels(self, *args):
        self.views.fft_canvas.axes.set_ylabel('幅度 / code')
        self.views.fft_canvas.draw_idle()

    def _registry_changed(self):
        self.ready = False
        self._buttons()

    def _available(self):
        return (self._link_state.get('connected') and not self._link_state.get('sending_paused')
                and self._link_state.get('idle', False) and not self.busy and not self.closing)

    def _buttons(self):
        available = bool(self._available())
        try:
            size = len(encode_text(self.send_edit.toPlainText()))
            valid = True
            self.byte_label.setText('{} / 256 UTF-8 字节'.format(size))
        except (ValueError, UnicodeError):
            valid = False
            self.byte_label.setText('超出 256 UTF-8 字节或含无效字符，请缩短文本。')
        self.prepare_button.setEnabled(available and not self.running and not self.tx_pending)
        self.send_button.setEnabled(available and self.ready and valid and not self.tx_pending)
        self.abort_button.setEnabled(available and self.ready)
        self.start_button.setEnabled(available and self.ready and not self.running)
        self.stop_button.setEnabled(self.running and not self.closing)
        self.registry_edit.setEnabled(not self.busy and not self.running and not self.tx_pending)
        self.registry_button.setEnabled(self.registry_edit.isEnabled())
        self.export_button.setEnabled(self.views.snapshot is not None and not self.closing)

    def _state_changed(self, state):
        self._link_state = state
        self.connection_label.setText('{} · {}'.format(state.get('port') or '未连接',
                                      '串口在线' if state.get('connected') else '请先连接串口'))
        if not state.get('connected') or state.get('sending_paused'):
            self.ready = self.running = self.tx_pending = False
            self._cancel.set()
            self.timer.stop()
            if not self.busy and self.link.rf_reserved:
                self.link.release_rf()
            self.profile_label.setText('连接或发送已停止；恢复后请重新检查 RF 会话。')
        self._buttons()

    def _submit(self, operation, payload):
        if not self._available():
            return False
        if not self.link.rf_reserved and not self.link.reserve_rf():
            return False
        self.busy = True
        if not self.link.submit_rf(operation, payload):
            self.busy = False
            if not self.running and not self.tx_pending:
                self.link.release_rf()
            self._buttons()
            return False
        self._buttons()
        return True

    def prepare(self):
        if self._submit('RF_PREPARE', dict(registry=self.registry_edit.text())):
            self.ready = False
            self.profile_label.setText('正在检查并绑定；未绑定设备将消耗一个新会话区间。')

    def send_text(self):
        text = self.send_edit.toPlainText()
        try:
            encode_text(text)
        except (ValueError, UnicodeError):
            self._buttons()
            return
        if self.ready and self._submit('RF_SEND', dict(text=text, sequence=self.sequence)):
            self.sequence = (self.sequence + 1) & 65535
            self.tx_label.setText('正在装载并请求发送；不会自动重发。')

    def start_receiving(self):
        if not self.ready or not self._available() or not self.link.reserve_rf():
            return
        self._cancel = Event()
        self.running = True
        self.status_label.setText('接收已启动；优先读取文字，再刷新 ADC 片段。')
        self.timer.start(0)
        self._buttons()

    def stop_receiving(self):
        self.running = False
        self._cancel.set()
        self.status_label.setText('电脑端接收已停止，保留已收到的文字与波形。')
        if not self.tx_pending:
            self.timer.stop()
            if not self.busy:
                self.link.release_rf()
        self._buttons()

    def abort_tx(self):
        self._submit('RF_ABORT_TX', {})

    def _poll(self):
        if self.closing or not (self.running or self.tx_pending):
            return
        if not self._available():
            self.timer.start(100)
            return
        if self.running:
            payload = dict(waveform=self.waveform_check.isChecked(),
                           count=self.count_combo.currentData(), cancel=self._cancel)
            self._submit('RF_POLL', payload)
        else:
            self._submit('RF_STATUS', {})

    def _display_result(self, result):
        message = result.get('message')
        if message is not None:
            identity = (message.session, message.generation)
            if identity != self._last_message:
                try:
                    text = message.text()
                except UnicodeError:
                    text = '[非 UTF-8 数据，十六进制] ' + message.payload.hex(' ')
                self.received_text.appendPlainText('{} · 序号 {} · {} 字节\n{}'.format(
                    datetime.now().strftime('%H:%M:%S'), message.sequence, len(message.payload), text))
                self._last_message = identity
        capture = result.get('capture')
        if capture is not None:
            config = CaptureConfig(capture.planned, capture.sample_rate, WaveConfig('external_adc'))
            snapshot = make_digital_snapshot(config, capture)
            self.views.set_snapshot(snapshot)
            self._fit_plot_labels()
            self.segment_count += 1
            if self.running:
                self.status_label.setText('自动刷新 · 已校验 {} 段 · 当前 {} 点 · CRC32 通过\n段间有空隙；原始码未校准。'.format(
                    self.segment_count, capture.planned))

    def _completed(self, operation, result):
        if self.closing:
            return
        self.busy = False
        if operation == 'RF_PREPARE':
            self.ready = True
            self.profile_label.setText('会话 {:08X} · 7 MHz / 1 MHz\n标称 25 MSa/s · 外部 ADC，诊断回环关闭。'.format(result['session']))
            if result['status'].tx_busy:
                self.tx_pending = True
                self.tx_label.setText('查询到 FPGA 正在发送；等待结束，不重新装载文本。')
        elif operation == 'RF_SEND':
            self.tx_pending = True
            self.tx_label.setText('已提交 {} 字节 · 序号 {}，等待 FPGA 发送完成。'.format(result['bytes'], result['sequence']))
        elif operation == 'RF_ABORT_TX':
            self.tx_pending = False
            self.tx_label.setText('FPGA 已确认中止发送。')
        else:
            self._display_result(result)
            status = result.get('status')
            if self.tx_pending and status is not None and not status.tx_busy:
                self.tx_pending = False
                self.tx_label.setText('FPGA 发送结束，错误码 {}；请检查设备状态。'.format(status.tx_error)
                                      if status.tx_error else 'FPGA 发送结束；是否送达请以对端接收结果为准。')
        if self.running or self.tx_pending:
            self.timer.start(150)
        else:
            self.link.release_rf()
        self._buttons()

    def _failed(self, report):
        if self.closing:
            return
        self.busy = self.running = self.ready = self.tx_pending = False
        self._cancel.set()
        self.timer.stop()
        if report.get('result'):
            self._display_result(report['result'])
        self.status_label.setText('任务已停止，未自动重试：' + report['error'])
        self.tx_label.setText('若发送应答丢失，结果未知；请先查询设备，不要盲目重发。')
        self.log_message.emit('RF：' + report['error'])
        self._buttons()

    def export_current(self):
        folder = QFileDialog.getExistingDirectory(self, '选择 ADC 快照导出目录')
        if folder and self.views.snapshot is not None:
            try:
                path = export_snapshot(self.views.snapshot, folder)
                self.status_label.setText('当前 ADC 快照已导出：' + str(path))
            except (OSError, ValueError) as exc:
                self.status_label.setText('导出失败，当前快照保留：' + str(exc))

    def shutdown(self):
        self.closing = True
        self.running = self.tx_pending = False
        self._cancel.set()
        self.timer.stop()
        self.views.shutdown()
