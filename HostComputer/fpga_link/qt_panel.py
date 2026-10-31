from datetime import datetime
from dataclasses import asdict
from threading import Event

from PyQt5.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt5.QtWidgets import (QWidget, QComboBox, QPushButton, QLabel, QFrame,
                             QVBoxLayout, QHBoxLayout, QGridLayout, QPlainTextEdit,
                             QSpinBox, QProgressBar, QFileDialog, QTabWidget, QScrollArea, QSizePolicy, QLayout)
from serial.tools import list_ports
from .serial_client import SerialClient
from .diagnostics import save_diagnostics
from .qt_worker import LinkWorker
from .qt_echo import EchoBox
from .qt_file_echo import FileEchoBox
from .qt_config import ConfigBox


class FpgaPanel(QWidget):
    request = pyqtSignal(str, object)
    connection_changed = pyqtSignal(bool, str)
    link_state_changed = pyqtSignal(object)
    log_message = pyqtSignal(str)
    shutdown_finished = pyqtSignal()
    digital_completed = pyqtSignal(str, object)
    digital_failed = pyqtSignal(object)
    digital_progress = pyqtSignal(object)
    rf_completed = pyqtSignal(str, object)
    rf_failed = pyqtSignal(object)

    def __init__(self, client_factory=None, heartbeat_ms=2000, parent=None):
        super().__init__(parent)
        self.connected = self.busy = False
        self.closing = False
        self.sending_paused = False
        self._active_operation = None
        self._pending_request = None
        self._digital_cancel = None
        self.rf_reserved = False
        self.confirmed_operations = 0
        self.last_batch = None
        self.last_echo = None
        self.last_file = None
        self.last_config = None
        self._supports_config = False
        self._file_cancel = None
        self._supports_echo = False
        self._batch_cancel = None
        self._port = ''
        self._device_info = None
        self._build_ui()
        self.activity_timer = QTimer(self)
        self.activity_timer.setSingleShot(True)
        self.activity_timer.timeout.connect(self._activity_idle)
        self.thread = QThread(self)
        self.worker = LinkWorker(client_factory or SerialClient)
        self.worker.moveToThread(self.thread)
        self.request.connect(self.worker.execute)
        self.worker.completed.connect(self._completed)
        self.worker.failed.connect(self._failed)
        self.worker.progress.connect(self._batch_progress)
        self.worker.file_progress.connect(self._file_progress)
        self.worker.digital_progress.connect(self.digital_progress)
        self.worker.digital_failed.connect(self._digital_failed)
        self.worker.rf_failed.connect(self._rf_failed)
        self.worker.stopped.connect(self.worker.deleteLater)
        self.worker.stopped.connect(self.thread.quit, Qt.DirectConnection)
        self.thread.finished.connect(self.shutdown_finished)
        self.thread.start()
        self.heartbeat = QTimer(self)
        self.heartbeat.timeout.connect(self.check_connection)
        if heartbeat_ms:
            self.heartbeat.start(heartbeat_ms)
        self.refresh_ports()
        self._update_buttons()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName('fpgaScroll')
        self.scroll_area.viewport().setObjectName('fpgaScrollViewport')
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QFrame()
        content.setFrameShape(QFrame.NoFrame)
        content.setObjectName('fpgaScrollContent')
        content.setAttribute(Qt.WA_StyledBackground, True)
        layout = QVBoxLayout(content)
        layout.setSizeConstraint(QLayout.SetMinimumSize)
        layout.setContentsMargins(0, 0, 0, 0)
        self.scroll_area.setWidget(content)
        content.setAutoFillBackground(False)
        outer.addWidget(self.scroll_area)
        layout.setSpacing(16)
        connection = QFrame()
        connection.setObjectName('sectionPanel')
        connection.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        box = QVBoxLayout(connection)
        box.setContentsMargins(20, 16, 20, 16)
        row = QHBoxLayout()
        label = QLabel('串口')
        self.port_combo = QComboBox()
        self.port_combo.setEditable(True)
        self.port_combo.setMinimumWidth(150)
        self.port_combo.setAccessibleName('FPGA 串口号')
        label.setBuddy(self.port_combo)
        self.refresh_button = QPushButton('刷新串口')
        self.connect_button = QPushButton('连接并验证')
        self.connect_button.setObjectName('primaryButton')
        self.disconnect_button = QPushButton('断开')
        row.addWidget(label)
        row.addWidget(self.port_combo, 1)
        row.addWidget(self.refresh_button)
        row.addWidget(QLabel('115200 · 8N1'))
        row.addWidget(self.connect_button)
        row.addWidget(self.disconnect_button)
        box.addLayout(row)
        grid = QGridLayout()
        self.connection_label = QLabel('未连接')
        self.firmware_label = QLabel('等待设备回复')
        self.firmware_label.setWordWrap(True)
        self.state_label = QLabel('未知')
        self.reply_label = QLabel('尚未收到')
        self.count_label = QLabel('0')
        self.latency_label = QLabel('—')
        fields = [('连接状态', self.connection_label), ('固件信息', self.firmware_label),
                  ('设备请求状态', self.state_label), ('最近回复', self.reply_label),
                  ('已确认操作', self.count_label), ('最近操作耗时', self.latency_label)]
        for i, (title, widget) in enumerate(fields):
            grid.addWidget(QLabel(title), i // 2, (i % 2) * 2)
            grid.addWidget(widget, i // 2, (i % 2) * 2 + 1)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 2)
        grid.addWidget(QLabel('通信活动'), 3, 0)
        self.activity_label = QLabel('○ 空闲')
        self.activity_label.setAccessibleName('串口通信活动指示')
        self.activity_label.setMinimumWidth(150)
        grid.addWidget(self.activity_label, 3, 1)
        self.pause_button = QPushButton('暂停发送')
        self.pause_button.setToolTip('暂停自动心跳并取消连续测试；不发送 FPGA STOP。继续后不自动重跑已取消测试。')
        grid.addWidget(self.pause_button, 3, 2)
        box.addLayout(grid)
        self.error_label = QLabel('')
        self.error_label.setObjectName('fpgaError')
        self.error_label.setWordWrap(True)
        box.addWidget(self.error_label)
        layout.addWidget(connection)
        actions = QHBoxLayout()
        self.ping_button = QPushButton('PING 检查通信')
        self.start_button = QPushButton('发送 START')
        self.stop_button = QPushButton('发送 STOP')
        self.reset_button = QPushButton('发送 RESET')
        for button in (self.ping_button, self.start_button, self.stop_button, self.reset_button):
            actions.addWidget(button)
        actions.addStretch(1)
        layout.addLayout(actions)
        diagnostics_page = QWidget()
        diagnostics_page.setObjectName('fpgaDiagnostics')
        diagnostics_layout = QVBoxLayout(diagnostics_page)
        diagnostics_layout.setContentsMargins(8, 8, 8, 8)
        batch = QHBoxLayout()
        batch.addWidget(QLabel('连续测试次数'))
        self.test_count = QSpinBox()
        self.test_count.setRange(1, 10000)
        self.test_count.setValue(1000)
        self.test_count.setAccessibleName('连续 PING 测试次数')
        self.batch_button = QPushButton('连续 PING')
        self.cancel_button = QPushButton('取消测试')
        self.batch_progress = QProgressBar()
        self.batch_progress.setRange(0, 1000)
        self.batch_progress.setValue(0)
        self.batch_progress.setFormat('通过 %v / %m')
        self.clear_log_button = QPushButton('清屏')
        self.clear_log_button.setToolTip('只清空通信日志显示；保留连接、状态及测试结果')
        self.clear_log_button.setAccessibleName('清空通信日志显示')
        self.clear_log_button.clicked.connect(self.clear_log)
        self.export_button = QPushButton('导出日志与结果')
        self.export_button.setToolTip('将本窗口日志和最近一次连续测试结果保存为 JSON')
        for widget in (self.test_count, self.batch_button, self.cancel_button):
            batch.addWidget(widget)
        batch.addWidget(self.batch_progress, 1)
        batch.addWidget(self.clear_log_button)
        batch.addWidget(self.export_button)
        diagnostics_layout.addLayout(batch)
        self.batch_summary = QLabel('连续测试尚未运行。测试只发送 PING，不发送控制命令。')
        self.batch_summary.setWordWrap(True)
        self.batch_summary.setObjectName('hintLabel')
        diagnostics_layout.addWidget(self.batch_summary)
        hint = QLabel('当前为仅通信测试，尚未控制基带。每 2 秒检查连接；暂停发送会暂停心跳并取消连续测试，不发送 STOP。恢复后需手动重跑测试。')
        hint.setObjectName('hintLabel')
        hint.setWordWrap(True)
        diagnostics_layout.addWidget(hint)
        self.communication_log = QPlainTextEdit()
        self.communication_log.setReadOnly(True)
        self.communication_log.setMaximumBlockCount(2000)
        self.communication_log.setAccessibleName('FPGA 真实通信操作与应答日志')
        self.echo_box = EchoBox()
        self.echo_box.submitted.connect(lambda data: self.submit('ECHO', data))
        self.data_tabs = QTabWidget()
        self.data_tabs.setObjectName('fpgaDataTabs')
        self.data_tabs.tabBar().setObjectName('fpgaDataTabBar')
        self.communication_log.setMinimumHeight(100)
        diagnostics_layout.addWidget(self.communication_log, 1)
        self.data_tabs.addTab(diagnostics_page, '通信日志')
        self.data_tabs.addTab(self.echo_box, '数据回传校验')
        self.file_box = FileEchoBox()
        self.file_box.submitted.connect(self.start_file)
        self.file_box.cancelled.connect(self.cancel_file)
        self.file_box.exported.connect(lambda: self.export_report())
        self.data_tabs.addTab(self.file_box, '文件回传校验')
        self.config_box = ConfigBox()
        self.config_box.submitted.connect(self.submit)
        self.data_tabs.addTab(self.config_box, '参数配置')
        layout.addWidget(self.data_tabs, 1)
        self.refresh_button.clicked.connect(self.refresh_ports)
        self.connect_button.clicked.connect(self.connect_device)
        self.disconnect_button.clicked.connect(lambda: self.submit('disconnect'))
        self.ping_button.clicked.connect(lambda: self.submit('PING'))
        self.pause_button.clicked.connect(self.toggle_sending)
        self.batch_button.clicked.connect(lambda: self.start_batch(self.test_count.value()))
        self.cancel_button.clicked.connect(self.cancel_batch)
        self.export_button.clicked.connect(lambda: self.export_report())
        for button, command in ((self.start_button, 'START'), (self.stop_button, 'STOP'), (self.reset_button, 'RESET')):
            button.clicked.connect(lambda checked=False, command=command: self.submit(command))

    def refresh_ports(self):
        selected = self.selected_port()
        self.port_combo.clear()
        try:
            for port in list_ports.comports():
                self.port_combo.addItem('{} · {}'.format(port.device, port.description), port.device)
            index = self.port_combo.findData(selected)
            if index >= 0:
                self.port_combo.setCurrentIndex(index)
            elif selected:
                self.port_combo.setEditText(selected)
        except Exception as exc:
            self.error_label.setText('枚举串口失败：' + str(exc))

    def selected_port(self):
        index = self.port_combo.currentIndex()
        text = self.port_combo.currentText().strip()
        if index >= 0 and text == self.port_combo.itemText(index):
            return self.port_combo.itemData(index) or text
        return text

    def connect_device(self):
        port = self.selected_port()
        if not port:
            self.error_label.setText('未发现串口。接好 USB_UART 后刷新，或输入串口号。')
            return
        self._port = port
        self.submit('connect', port)

    def submit(self, operation, payload=None):
        if self.rf_reserved and not operation.startswith('RF_') and operation != 'disconnect':
            return False
        if self.closing or (self.sending_paused and operation not in ('connect', 'disconnect')):
            return False
        if self.busy:
            if self._active_operation == 'heartbeat' and operation != 'heartbeat' and self._pending_request is None:
                self._pending_request = operation, payload
                self._update_buttons()
                return True
            return False
        if not self.connected and operation != 'connect':
            return False
        if operation in ('CONFIG_GET', 'CONFIG_SET') and not self._supports_config:
            return
        if operation in ('ECHO', 'FILE') and not self._supports_echo:
            return
        if operation in ('CONFIG_GET', 'CONFIG_SET'):
            self.last_config = {'status': 'running', 'operation': operation,
                                'requested': asdict(payload) if payload is not None else None,
                                'readback': None}
            self.config_box.result_label.setText('正在读取…' if operation == 'CONFIG_GET' else '正在写入并独立读回…')
        self.busy = True
        self._active_operation = operation
        self.error_label.clear()
        self._pulse_activity()
        if operation not in ('heartbeat', 'RF_POLL', 'RF_STATUS'):
            self.connection_label.setText('正在验证…' if operation == 'connect' else '等待应答…')
        if operation == 'ECHO':
            self.last_echo = {'status': 'running', 'sent_hex': payload.hex(' '),
                              'received_hex': '', 'byte_count': len(payload)}
            self.echo_box.started(len(payload))
        if operation == 'batch':
            self._log('开始连续 PING：{} 次，不自动重发'.format(payload['count']))
        elif operation not in ('heartbeat', 'RF_POLL', 'RF_STATUS'):
            self._log('发送 {}{}'.format(operation, ' ' + str(payload) if payload else ''))
        self._update_buttons()
        self.request.emit(operation, payload)
        return True

    def submit_digital(self, operation, payload):
        if operation not in ('DIGITAL_INFO', 'DIGITAL_CAPTURE', 'DIGITAL_STATUS', 'DIGITAL_CANCEL', 'DIGITAL_RELEASE'):
            return False
        accepted = self.submit(operation, dict(payload))
        if accepted:
            self._digital_cancel = payload.get('cancel')
        return accepted

    def reserve_rf(self):
        if (self.closing or not self.connected or self.sending_paused
                or self.busy or self._pending_request is not None):
            return False
        self.rf_reserved = True
        self._update_buttons()
        return True

    def release_rf(self):
        self.rf_reserved = False
        self._update_buttons()

    def submit_rf(self, operation, payload):
        if not self.rf_reserved or operation not in (
                'RF_PREPARE', 'RF_SEND', 'RF_POLL', 'RF_STATUS', 'RF_ABORT_TX'):
            return False
        return self.submit(operation, dict(payload))

    def _rf_failed(self, report):
        if self.closing:
            return
        self.busy = False
        self._active_operation = None
        self.rf_reserved = False
        if report['fatal']:
            self._failed(report['operation'], report['error'])
        else:
            self.connection_label.setText(self._port + ' · 在线')
            self._update_buttons()
        self.rf_failed.emit(report)

    def _drop_pending(self, reason):
        pending, self._pending_request = self._pending_request, None
        if pending and pending[0].startswith('DIGITAL_'):
            self.digital_failed.emit(dict(operation=pending[0], source='local',
                                          error=reason, code=None, partial=b''))

    def _digital_failed(self, report):
        if self.closing:
            return
        if report['source'] != 'link':
            self.busy = False
            self._active_operation = None
            self._digital_cancel = None
            self.connection_label.setText(self._port + ' · 在线')
            self._update_buttons()
        self._log('{}：{}'.format(report['operation'], report['error']))
        self.digital_failed.emit(report)

    def check_connection(self):
        if self.connected and not self.sending_paused:
            self.submit('heartbeat')

    def _pulse_activity(self):
        if self.sending_paused or self.closing:
            return
        self.activity_label.setText('● 通信中')
        self.activity_timer.start(250)

    def _activity_idle(self):
        self.activity_label.setText('○ 已暂停' if self.sending_paused else '○ 空闲')

    def toggle_sending(self):
        if self.closing or not self.connected:
            return
        self.sending_paused = not self.sending_paused
        if self.sending_paused:
            self._drop_pending('发送已暂停，排队的数字源任务已取消。')
            if self._digital_cancel is not None:
                self._digital_cancel.set()
            self.cancel_batch()
            self.cancel_file()
            self.activity_timer.stop()
            self._activity_idle()
            self._log('已暂停电脑端发送；当前请求完成后不再发送。未发送 STOP。')
        else:
            self._activity_idle()
            self._log('已继续发送，恢复自动心跳；已取消的连续测试需手动重新运行。')
        self._update_buttons()

    def start_file(self, path):
        if self.closing or self.sending_paused or not self.connected or not self._supports_echo:
            return
        if self.busy:
            if self._active_operation == 'heartbeat' and self._pending_request is None:
                self._pending_request = 'file_path', path
                self._update_buttons()
            return
        self._file_cancel = Event()
        self.last_file = None
        self.file_box.started()
        self.submit('FILE', {'path': path, 'cancel': self._file_cancel})

    def cancel_file(self):
        if self._file_cancel is not None:
            self._file_cancel.set()
            self.file_box.cancel_button.setEnabled(False)

    def _file_progress(self, report):
        if not self.closing:
            self.file_box.update_report(report)
            self._pulse_activity()

    def start_batch(self, count):
        if self.busy and self._active_operation == 'heartbeat' and self._pending_request is None and not self.sending_paused:
            self._pending_request = 'batch_count', count
            self._update_buttons()
            return
        if self.busy or self.closing or self.sending_paused or not self.connected:
            return
        if type(count) is not int or not 1 <= count <= 10000:
            raise ValueError('连续测试次数必须为 1 到 10000')
        self._batch_cancel = Event()
        self.last_batch = None
        self.batch_progress.setRange(0, count)
        self.batch_progress.setValue(0)
        self.batch_summary.setText('连续测试进行中…')
        self.submit('batch', {'count': count, 'cancel': self._batch_cancel})

    def cancel_batch(self):
        if self._batch_cancel is not None:
            self._batch_cancel.set()
            self.cancel_button.setEnabled(False)
            self.batch_summary.setText('正在取消，等待当前这次应答结束…')

    def _batch_progress(self, report):
        if self.closing:
            return
        self.batch_progress.setValue(report['passed'])
        self._pulse_activity()
        if self._batch_cancel is not None and self._batch_cancel.is_set():
            return
        self.batch_summary.setText('已通过 {} / {}，已用时 {:.1f} 秒'.format(
            report['passed'], report['planned'], report['elapsed_seconds']))

    def _completed(self, operation, result):
        if self.closing:
            return
        self.busy = False
        self._active_operation = None
        if not self.sending_paused and operation != 'disconnect':
            self._pulse_activity()
        if operation.startswith('RF_'):
            self.connection_label.setText(self._port + ' · 在线')
            self.reply_label.setText(datetime.now().strftime('%H:%M:%S'))
            self._update_buttons()
            self.rf_completed.emit(operation, result)
            return
        if operation.startswith('DIGITAL_'):
            self._digital_cancel = None
            self.connection_label.setText(self._port + ' · 在线')
            self.reply_label.setText(datetime.now().strftime('%H:%M:%S'))
            self._log(operation + ' 已确认')
            self._update_buttons()
            self.digital_completed.emit(operation, result)
            return
        if operation in ('CONFIG_GET', 'CONFIG_SET'):
            config, elapsed_ms = result
            self.last_config.update(status='passed', readback=asdict(config), elapsed_ms=elapsed_ms)
            self.config_box.completed(config, operation == 'CONFIG_SET')
            self._log(self.config_box.result_label.text())
            self.confirmed_operations += 1
            self.count_label.setText(str(self.confirmed_operations))
            self.connection_label.setText(self._port + ' · 在线')
            self.reply_label.setText(datetime.now().strftime('%H:%M:%S'))
            self.latency_label.setText('{:.0f} ms'.format(elapsed_ms))
            self._update_buttons()
            return
        if operation == 'FILE':
            self.last_file = result
            self._file_cancel = None
            self.file_box.update_report(result)
            self.confirmed_operations += result['chunks_passed']
            self.count_label.setText(str(self.confirmed_operations))
            self._log('文件回传 ' + self.file_box.result_label.text())
            if result['status'] == 'failed':
                if result.get('error_source') != 'file':
                    self._failed(operation, result['error'])
                    return
                self.error_label.setText('本地文件处理失败，串口连接保留。请检查文件后重试。' + result['error'])
                self._log('本地文件错误；串口连接保留，可检查文件后重试。')
            self.connection_label.setText(self._port + ' · 在线')
            self._update_buttons()
            return
        if operation == 'batch':
            info, elapsed_ms, report = result
            self._batch_cancel = None
            self.last_batch = report
            self.confirmed_operations += report['passed']
            self.count_label.setText(str(self.confirmed_operations))
            self.batch_progress.setValue(report['passed'])
            status = {'passed': '通过', 'cancelled': '已取消', 'failed': '失败'}[report['status']]
            summary = '{}：通过 {} / {}，失败 {}，用时 {:.1f} 秒'.format(
                status, report['passed'], report['planned'], report['failed'], report['elapsed_seconds'])
            if report['rtt_ms']['mean'] is not None:
                summary += '；往返耗时平均 {:.1f} ms / 最大 {:.1f} ms'.format(
                    report['rtt_ms']['mean'], report['rtt_ms']['max'])
            self.batch_summary.setText(summary)
            self._log('连续 PING ' + summary)
            if report['status'] == 'failed':
                self._failed(operation, report['error'])
                return
            if info is None:
                self.connection_label.setText(self._port + ' · 在线')
                self._update_buttons()
                return
            result = info, elapsed_ms
        if operation == 'ECHO':
            received, elapsed_ms = result
            self.last_echo.update(status='passed', received_hex=received.hex(' '), elapsed_ms=elapsed_ms)
            self.echo_box.completed(received, elapsed_ms)
            self._log('数据回传校验通过：{} 字节逐字节一致'.format(len(received)))
            result = None, elapsed_ms
        if operation == 'disconnect':
            self._offline('已断开')
            self._log('串口已关闭；设备当前状态未知')
        else:
            info, elapsed_ms = result
            self.connected = True
            self.connection_label.setText(self._port + ' · 在线')
            if info is not None:
                self._device_info = info
                self._supports_echo = info.supports_echo
                self._supports_config = info.supports_config
                self.firmware_label.setText('仅通信测试 · 协议 {}.{} · COMM_ONLY=1 · 数据回传{}'.format(
                    info.major, info.minor, '可用' if info.supports_echo else '不支持'))
                self.firmware_label.setText(self.firmware_label.text() + ' · 参数配置' + ('可用' if info.supports_config else '不支持'))
                self.state_label.setText('请求运行（已确认）' if info.requested_running else '请求停止（已确认）')
            self.reply_label.setText(datetime.now().strftime('%H:%M:%S'))
            self.latency_label.setText('{:.0f} ms'.format(elapsed_ms))
            if operation != 'batch':
                self.confirmed_operations += 1
            self.count_label.setText(str(self.confirmed_operations))
            if operation not in ('heartbeat', 'batch'):
                reply = 'ACK + PONG' if operation in ('START', 'STOP', 'RESET') else ('ECHO_REPLY' if operation == 'ECHO' else 'PONG')
                self._log('{} 成功：{}；{}'.format(operation, reply, self.state_label.text()))
            self.connection_changed.emit(True, self._port)
        self._update_buttons()
        if self._pending_request is not None:
            pending, self._pending_request = self._pending_request, None
            if pending[0] == 'file_path':
                self.start_file(pending[1])
            elif pending[0] == 'batch_count':
                self.start_batch(pending[1])
            else:
                self.submit(*pending)

    def _failed(self, operation, message):
        if self.closing:
            return
        self.busy = False
        self._active_operation = None
        self._drop_pending('通信失败，排队的数字源任务未发送。')
        self._digital_cancel = None
        self._batch_cancel = None
        self._file_cancel = None
        if operation in ('CONFIG_GET', 'CONFIG_SET'):
            self.last_config.update(status='failed', error=message)
            self.config_box.result_label.setText('配置未确认：' + message)
        if operation == 'FILE':
            self.file_box.running = False
            self.file_box.result_label.setText('文件回传失败：' + message)
        if operation == 'ECHO':
            self.last_echo.update(status='failed', error=message)
            self.echo_box.failed(message)
        self._offline('通信失败')
        self.error_label.setText('通信失败，指令结果未确认。请重新连接后查询状态。' + message)
        self._log('{} 失败：{}'.format(operation, message))
        self._update_buttons()

    def _offline(self, text):
        self.rf_reserved = False
        self._device_info = None
        self._supports_config = False
        self.config_box.result_label.setText('设备参数未确认；历史结果可导出，重新连接后请读取。')
        self.connected = False
        self._supports_echo = False
        self.activity_timer.stop()
        self.activity_label.setText('○ 未连接')
        self.connection_label.setText(text)
        self.firmware_label.setText('等待设备回复')
        self.state_label.setText('未知')
        self.connection_changed.emit(False, '')

    def _update_buttons(self):
        available = (not self.busy or (self._active_operation == 'heartbeat' and self._pending_request is None)) and not self.closing
        can_send = available and self.connected and not self.sending_paused and not self.rf_reserved
        self.port_combo.setEnabled(available and not self.connected)
        self.refresh_button.setEnabled(available and not self.connected)
        self.connect_button.setEnabled(available and not self.connected)
        self.disconnect_button.setEnabled(available and self.connected)
        for button in (self.ping_button, self.start_button, self.stop_button, self.reset_button):
            button.setEnabled(can_send)
        self.echo_box.set_available(can_send, self._supports_echo)
        self.file_box.set_available(can_send, self._supports_echo)
        self.config_box.set_available(can_send, self._supports_config)
        self.batch_button.setEnabled(can_send)
        self.pause_button.setEnabled(self.connected and not self.closing)
        self.pause_button.setText('继续发送' if self.sending_paused else '暂停发送')
        self.test_count.setEnabled(available)
        self.cancel_button.setEnabled(self._batch_cancel is not None and not self.closing
                                      and not self._batch_cancel.is_set())
        self.clear_log_button.setEnabled(not self.closing)
        self.export_button.setEnabled(available and bool(
            self.communication_log.toPlainText() or self.last_batch or self.last_echo or self.last_file or self.last_config))
        self.link_state_changed.emit(self.link_state())

    def link_state(self):
        info = self._device_info
        return dict(connected=self.connected, port=self._port if self.connected else '',
                    protocol='{}.{}'.format(info.major, info.minor) if info else None,
                    sending_paused=self.sending_paused, busy=self.busy,
                    idle=(not self.busy or (self._active_operation == 'heartbeat' and self._pending_request is None)) and not self.closing,
                    available=(not self.busy or (self._active_operation == 'heartbeat' and self._pending_request is None)) and not self.closing and not self.rf_reserved,
                    supports_echo=self._supports_echo, supports_config=self._supports_config,
                    supports_capture=False, supports_dac=False)

    def clear_log(self):
        self.communication_log.clear()
        self._update_buttons()

    def export_report(self, path=None):
        if (self.busy and self._active_operation != 'heartbeat') or self.closing:
            return False
        if path is None:
            path, _ = QFileDialog.getSaveFileName(self, '导出通信日志与结果',
                'fpga_diagnostics_{}.json'.format(datetime.now().strftime('%Y%m%d_%H%M%S')), 'JSON (*.json)')
        if not path:
            return False
        report = {'schema_version': 1, 'kind': 'fpga_communication_diagnostics',
                  'exported_at': datetime.now().isoformat(timespec='seconds'),
                  'port': self._port, 'baud': 115200, 'connected_at_export': self.connected,
                  'sending_paused': self.sending_paused,
                  'firmware': self.firmware_label.text(), 'request_state': self.state_label.text(),
                  'confirmed_operations': self.confirmed_operations, 'batch': self.last_batch,
                  'echo': self.last_echo, 'file_echo': self.last_file, 'configuration': self.last_config,
                  'log': self.communication_log.toPlainText()}
        try:
            save_diagnostics(path, report)
        except (OSError, ValueError, TypeError) as exc:
            self.error_label.setText('导出失败，日志和结果仍保留在窗口中：' + str(exc))
            return False
        self.error_label.clear()
        self._log('诊断记录已保存：' + str(path))
        return True

    def _log(self, message):
        self.communication_log.appendPlainText('{} {}'.format(datetime.now().strftime('%H:%M:%S'), message))
        self.log_message.emit('FPGA 通信：' + message)

    def shutdown(self):
        if self.closing:
            return
        self.closing = True
        self._drop_pending('窗口关闭，排队的数字源任务未发送。')
        if self._digital_cancel is not None:
            self._digital_cancel.set()
        self.activity_timer.stop()
        self.cancel_batch()
        self.cancel_file()
        self.heartbeat.stop()
        self.connected = False
        self._update_buttons()
        self.request.emit('shutdown', None)
