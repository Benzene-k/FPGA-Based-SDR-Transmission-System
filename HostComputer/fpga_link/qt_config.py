from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QFrame,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,QPushButton,QSpinBox
from .configuration import CommConfig

class ConfigBox(QFrame):
    submitted = pyqtSignal(str, object)
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setObjectName('sectionPanel')
        layout=QVBoxLayout(self)
        hint=QLabel('仅保存通信模块参数，不驱动基带；断电/硬复位恢复默认。通信RESET不清除参数。')
        hint.setWordWrap(True);layout.addWidget(hint)
        form=QFormLayout()
        self.frame_spin=QSpinBox();self.frame_spin.setRange(2,4096);self.frame_spin.setValue(30)
        self.sync_spin=QSpinBox();self.sync_spin.setRange(1,1024);self.sync_spin.setValue(13)
        self.seed_spin=QSpinBox();self.seed_spin.setRange(0,2147483647);self.seed_spin.setValue(20260919)
        for title,widget in [('每帧符号数',self.frame_spin),('同步头长度（符号）',self.sync_spin),('随机种子',self.seed_spin)]:
            widget.setAccessibleName(title);form.addRow(title,widget)
        layout.addLayout(form)
        row=QHBoxLayout()
        self.read_button=QPushButton('读取FPGA参数')
        self.write_button=QPushButton('写入并读回核对')
        row.addWidget(self.read_button);row.addWidget(self.write_button);row.addStretch(1);layout.addLayout(row)
        self.support_label=QLabel('连接支持参数配置的新固件后可用。');self.support_label.setWordWrap(True);layout.addWidget(self.support_label)
        self.result_label=QLabel('尚未读取，输入框为本地默认值。');self.result_label.setWordWrap(True);layout.addWidget(self.result_label)
        layout.addStretch(1)
        self.read_button.clicked.connect(lambda:self.submitted.emit('CONFIG_GET',None))
        self.write_button.clicked.connect(self.write)
    def set_available(self,can_send,supported):
        for widget in (self.frame_spin,self.sync_spin,self.seed_spin,self.read_button,self.write_button):
            widget.setEnabled(can_send and supported)
        self.support_label.setText('配置可用；写入后另发读取请求核对，不自动重发。' if supported else '当前固件未启用参数配置；原有PING与回传仍可使用。')
    def write(self):
        config=CommConfig(self.frame_spin.value(),self.sync_spin.value(),self.seed_spin.value())
        try:config.validate()
        except ValueError:
            self.result_label.setText('输入错误：同步头长度必须小于每帧符号数。')
            return
        self.submitted.emit('CONFIG_SET',config)
    def completed(self,config,write=False):
        self.frame_spin.setValue(config.frame_symbols);self.sync_spin.setValue(config.sync_symbols);self.seed_spin.setValue(config.random_seed)
        self.result_label.setText(('写入并独立读回核对通过' if write else '读取成功')+'：每帧 {}，同步头 {}，种子 {}。仅通信寄存器。'.format(config.frame_symbols,config.sync_symbols,config.random_seed))
