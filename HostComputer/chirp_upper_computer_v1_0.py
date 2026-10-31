import sys

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QApplication, QLabel, QListWidgetItem
import chirp_upper_computer_v0_11 as legacy
from fpga_link.qt_panel import FpgaPanel
from adda.qt_panel import AddaPanel
from fpga_link.qt_rf import RfPanel

APP_TITLE = 'Chirp 上位机 V1.5.0 · 文本收发 / ADC'
APP_VERSION = '1.5.0'


class MainWindow(legacy.MainWindow):
    def __init__(self, client_factory=None, heartbeat_ms=2000):
        self._client_factory = client_factory
        self._heartbeat_ms = heartbeat_ms
        self._serial_close_started = False
        self._serial_closed = False
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.nav.setCurrentRow(self.rf_page_index)
        self.log('V1.5.0：文本 RF 收发、会话绑定与 25 MSa/s ADC 分段刷新；模拟与天线链路须单独验收。')

    def _build_ui(self):
        super()._build_ui()
        self.fpga_page_index = self.stack.count()
        page, layout = self._page_container('FPGA 通信', '验证电脑与 FPGA 的真实双向通信。连接后先检查 PONG，再发送控制请求并核对返回状态。')
        self.fpga_panel = FpgaPanel(self._client_factory, self._heartbeat_ms, page)
        self.fpga_panel.log_message.connect(self.log)
        self.fpga_panel.connection_changed.connect(self._show_fpga_status)
        self.fpga_panel.shutdown_finished.connect(self._serial_shutdown_finished)
        layout.addWidget(self.fpga_panel, 1)
        self.stack.addWidget(page)
        self.nav.addItem(QListWidgetItem('FPGA 通信'))
        self.adda_page_index = self.stack.count()
        adda_page, adda_layout = self._page_container('AD/DA 采集', '本地测试、板内数字源、真实 ADC 或文件导入；统一查看波形、频谱、统计和原始码并导出。本页保留单次采集；RF 控制与自动刷新见文本收发页。')
        self.adda_panel = AddaPanel(legacy.THEME, adda_page)
        adda_layout.addWidget(self.adda_panel, 1)
        self.adda_panel.open_communication.connect(lambda: self.nav.setCurrentRow(self.fpga_page_index))
        self.adda_panel.selection_changed.connect(self._adda_selection_changed)
        self.adda_panel.bind_link(self.fpga_panel)
        self.stack.addWidget(adda_page)
        self.nav.addItem(QListWidgetItem('AD/DA 采集'))
        self.rf_page_index = self.stack.count()
        rf_page, rf_layout = self._page_container('文本收发', '两台电脑各连接一块板。发送 UTF-8 文本，持续接收解码文字并刷新 ADC 片段；需要当前 RF 固件和本机专用会话账本。')
        self.rf_panel = RfPanel(legacy.THEME, self.fpga_panel, rf_page)
        self.rf_panel.open_communication.connect(lambda: self.nav.setCurrentRow(self.fpga_page_index))
        self.rf_panel.log_message.connect(self.log)
        rf_layout.addWidget(self.rf_panel, 1)
        self.stack.addWidget(rf_page)
        self.nav.addItem(QListWidgetItem('文本收发'))
        self.top_fpga.set_status('未连接', 'idle')
        self.work_mode_combo.setItemText(2, 'FPGA基带（待接入）')
        for label in self.findChildren(QLabel):
            if label.objectName() == 'brandSub':
                label.setText('射频通信实验平台 V1.5.0')
            elif label.text() == '数据源：模拟后端':
                self.data_source_label = label
                label.setText('实验数据：模拟 · FPGA：仅通信')

    def _apply_style(self):
        super()._apply_style()
        theme = legacy.THEME
        self.setStyleSheet(self.styleSheet() + ("""
QLabel#fpgaError { color: %(danger)s; }
QTabWidget#fpgaDataTabs::pane { border: 1px solid %(border_subtle)s; background: %(bg_app)s; }
QTabBar#fpgaDataTabBar { background: %(bg_app)s; }
QTabBar#fpgaDataTabBar::tab { background: %(bg_panel)s; color: %(text_secondary)s;
    border: 1px solid %(border_subtle)s; padding: 7px 14px; margin-right: 4px; }
QTabBar#fpgaDataTabBar::tab:selected { background: %(bg_selected)s; color: %(text_primary)s;
    border-bottom: 2px solid %(accent)s; }
QTabBar#fpgaDataTabBar::tab:focus { border: 1px solid %(border_focus)s; }
""" % theme))
        scroll = self.fpga_panel.scroll_area
        for widget in (scroll, scroll.viewport(), scroll.widget()):
            widget.setStyleSheet('#' + widget.objectName() + ' { background-color: ' + theme['bg_app'] + '; }')

    def _show_fpga_status(self, connected, port):
        self.top_fpga.set_status(port + ' 通信在线' if connected else '未连接', 'ok' if connected else 'idle')

    def _refresh_all(self):
        super()._refresh_all()
        if hasattr(self, 'fpga_panel'):
            self._show_fpga_status(self.fpga_panel.connected, self.fpga_panel._port)

    def _update_top_title(self, row):
        if row == getattr(self, 'rf_page_index', -1):
            self.top_title.setText('文本收发 / ADC')
            self.mode_badge.setText('● FPGA RF 收发')
            if hasattr(self, 'data_source_label'):
                self.data_source_label.setText('RF 文本消息 / ADC 原始码 · 模拟链路待验收')
            return
        adda_selected = row == getattr(self, 'adda_page_index', -1)
        imported = bool(adda_selected and self.adda_panel.displayed_snapshot
                        and self.adda_panel.displayed_snapshot.import_info)
        if adda_selected:
            self.top_title.setText('AD/DA 数据查看与分析')
            board = bool(self.adda_panel.displayed_snapshot and self.adda_panel.displayed_snapshot.digital_info)
            adc = bool(self.adda_panel.displayed_snapshot and self.adda_panel.displayed_snapshot.source == 'FPGA_EXTERNAL_ADC')
            self.mode_badge.setText('● 文件导入' if imported else ('● 真实 ADC' if adc else ('● 板内数字源' if board else '● 本地测试')))
        elif row == self.fpga_page_index:
            self.top_title.setText('FPGA 串口通信验证')
            self.mode_badge.setText('● FPGA 仅通信')
        else:
            super()._update_top_title(row)
            self.mode_badge.setText('● ' + self.work_mode_combo.currentText())
        if hasattr(self, 'data_source_label'):
            text = '实验数据：模拟 · FPGA：仅通信'
            if adda_selected:
                text = 'AD/DA：{} · 本页 DAC 仅预览'.format(self.adda_panel.source_text(self.adda_panel.displayed_snapshot))
            self.data_source_label.setText(text)

    def _adda_selection_changed(self, snapshot):
        if self.nav.currentRow() == self.adda_page_index:
            self._update_top_title(self.adda_page_index)

    def _validate_config(self, config):
        if config.work_mode != '模拟模式':
            return '基带功能尚未接入。请到“FPGA 通信”页进行串口与控制应答联调。'
        return super()._validate_config(config)

    def closeEvent(self, event):
        if self._serial_closed:
            super().closeEvent(event)
            return
        if self._serial_close_started:
            event.ignore()
            return
        super().closeEvent(event)
        if not event.isAccepted():
            return
        event.ignore()
        self._serial_close_started = True
        self.setEnabled(False)
        self.status_label.setText('正在关闭串口…')
        self.rf_panel.shutdown()
        self.adda_panel.shutdown()
        self.fpga_panel.shutdown()

    def _serial_shutdown_finished(self):
        self._serial_closed = True
        self.close()


def main():
    for attribute in ('AA_EnableHighDpiScaling', 'AA_UseHighDpiPixmaps'):
        if hasattr(Qt, attribute):
            QApplication.setAttribute(getattr(Qt, attribute), True)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_TITLE)
    app.setApplicationVersion(APP_VERSION)
    font = QFont(legacy.UI_FONT_FAMILY, 12)
    font.setWeight(QFont.Normal)
    app.setFont(font)
    window = MainWindow()
    window.show()
    return app.exec_()


if __name__ == '__main__':
    sys.exit(main())
