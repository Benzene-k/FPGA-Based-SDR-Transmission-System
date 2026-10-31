from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPlainTextEdit, QPushButton
from .protocol import MAX_PAYLOAD


class EchoBox(QFrame):
    submitted = pyqtSignal(bytes)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('sectionPanel')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        row = QHBoxLayout()
        label = QLabel('输入格式')
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(['文本（UTF-8）', '十六进制'])
        self.mode_combo.setAccessibleName('回传数据输入格式')
        self.mode_combo.setMinimumHeight(34)
        label.setBuddy(self.mode_combo)
        self.send_button = QPushButton('发送并校验回传')
        self.send_button.setObjectName('primaryButton')
        row.addWidget(label); row.addWidget(self.mode_combo)
        row.addStretch(1); row.addWidget(self.send_button)
        layout.addLayout(row)
        self.support_label = QLabel('单包 0–256 字节；中文按 UTF-8 字节计数。仅验证串口数据往返。')
        self.support_label.setWordWrap(True)
        self.support_label.setObjectName('hintLabel')
        layout.addWidget(self.support_label)
        columns = QHBoxLayout()
        self.input_edit = QPlainTextEdit()
        self.input_edit.setPlainText('你好 FPGA')
        self.input_edit.setAccessibleName('发送数据')
        self.input_edit.setPlaceholderText('文本，或空格分隔的十六进制，例如 00 AA 55 FF')
        self.received_edit = QPlainTextEdit()
        self.received_edit.setReadOnly(True)
        self.received_edit.setAccessibleName('FPGA 回传数据十六进制')
        for title, editor in [('发送内容', self.input_edit), ('回传内容（十六进制）', self.received_edit)]:
            editor.setMinimumHeight(80)
            column = QVBoxLayout(); label = QLabel(title); label.setBuddy(editor)
            column.addWidget(label); column.addWidget(editor, 1); columns.addLayout(column, 1)
        layout.addLayout(columns, 1)
        self.result_label = QLabel('尚未进行数据回传校验。')
        self.result_label.setWordWrap(True)
        layout.addWidget(self.result_label)
        self.send_button.clicked.connect(self._submit)

    def set_available(self, can_send, supported):
        self.send_button.setEnabled(can_send and supported)
        self.support_label.setText(
            '单包 0–256 字节；中文按 UTF-8 字节计数。仅验证串口数据往返。' if supported else
            '连接支持数据回传的通信固件后可测试；旧固件仍可使用 PING 和控制命令。')

    def _submit(self):
        text = self.input_edit.toPlainText()
        try:
            if len(text) > MAX_PAYLOAD * 3:
                raise ValueError('输入过长；单包最多 256 字节')
            payload = text.encode('utf-8') if self.mode_combo.currentIndex() == 0 else bytes.fromhex(text)
            if len(payload) > MAX_PAYLOAD:
                raise ValueError('编码后为 {} 字节；单包最多 256 字节'.format(len(payload)))
        except (ValueError, UnicodeError) as exc:
            self.result_label.setText('输入错误：{}'.format(exc))
            return
        self.submitted.emit(payload)

    def started(self, count):
        self.received_edit.clear()
        self.result_label.setText('正在发送并核对 {} 字节…'.format(count))

    def completed(self, payload, elapsed_ms):
        self.received_edit.setPlainText(payload.hex(' '))
        self.result_label.setText('校验通过：{} 字节逐字节一致；往返耗时 {:.1f} ms。'.format(
            len(payload), elapsed_ms))

    def failed(self, message):
        self.received_edit.clear()
        self.result_label.setText('回传校验失败：' + message)
