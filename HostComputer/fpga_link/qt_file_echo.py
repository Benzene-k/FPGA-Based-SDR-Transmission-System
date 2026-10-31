from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFileDialog, QProgressBar

class FileEchoBox(QFrame):
    submitted = pyqtSignal(str)
    cancelled = pyqtSignal()
    exported = pyqtSignal()
    def __init__(self, parent=None):
        super().__init__(parent)
        self.path = ''
        self.running = False
        self.setObjectName('sectionPanel')
        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        self.choose_button = QPushButton('选择文件')
        self.send_button = QPushButton('发送文件并校验')
        self.cancel_button = QPushButton('取消传输')
        self.export_button = QPushButton('导出诊断结果')
        for button in (self.choose_button,self.send_button,self.cancel_button,self.export_button): row.addWidget(button)
        layout.addLayout(row)
        self.path_label = QLabel('尚未选择文件'); self.path_label.setWordWrap(True);layout.addWidget(self.path_label)
        hint=QLabel('每块最多256字节，逐块回传并核对整文件SHA-256；不在FPGA保存文件。取消后不自动续传。')
        hint.setWordWrap(True);layout.addWidget(hint)
        self.choose_button.setAccessibleName('选择回传校验文件')
        self.send_button.setAccessibleName('开始文件分块回传校验')
        self.progress = QProgressBar(); self.progress.setRange(0,1000);layout.addWidget(self.progress)
        self.result_label=QLabel('尚未传输');self.result_label.setWordWrap(True);layout.addWidget(self.result_label)
        layout.addStretch(1)
        self.choose_button.clicked.connect(self.choose)
        self.send_button.clicked.connect(lambda: self.submitted.emit(self.path))
        self.cancel_button.clicked.connect(self.cancelled.emit)
        self.export_button.clicked.connect(self.exported.emit)
    def choose(self):
        path,_=QFileDialog.getOpenFileName(self,'选择回传校验文件','','所有文件 (*)')
        if path:
            self.path=path;self.path_label.setText(path)
            self.send_button.setEnabled(True)
    def set_available(self, can_send, supported):
        self.choose_button.setEnabled(can_send and supported)
        self.send_button.setEnabled(can_send and supported and bool(self.path))
        self.cancel_button.setEnabled(self.running)
        self.export_button.setEnabled(not self.running)
    def started(self):
        self.running=True; self.progress.setValue(0);self.result_label.setText('正在传输…')
    def update_report(self, report):
        passed=report['status']=='passed'
        total=report['total_bytes'];done=report['verified_bytes']
        self.progress.setValue(1000 if passed else (int(done*1000/total) if total else 0))
        status={'running':'传输中','passed':'通过','cancelled':'已取消','failed':'失败'}[report['status']]
        self.result_label.setText('{}：已核对 {} / {} 字节，{} 块，用时 {:.1f} 秒。{}'.format(status,done,total,report['chunks_passed'],report['elapsed_seconds'],report['error']))
        if passed:
            self.result_label.setText(self.result_label.text()+'\n发送与回传 SHA-256：'+report['source_sha256'])
        self.running=report['status']=='running'
