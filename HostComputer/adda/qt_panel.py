from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
                             QBoxLayout, QFormLayout, QComboBox, QDoubleSpinBox,
                             QGroupBox, QProgressBar, QScrollArea, QFileDialog)
from threading import Event

from .analysis import statistics
from .controller import CaptureController
from .export import export_snapshot
from .models import CaptureConfig, make_snapshot
from .qt_widgets import WaveEditor, RawCanvas
from .sources import LocalTestSource
from .qt_views import SnapshotViews
from .history import RecentSnapshots
from .importer import import_package
from .image_export import export_png
from .qt_digital import DigitalCaptureBox


class AddaPanel(QWidget):
    open_communication = pyqtSignal()
    selection_changed = pyqtSignal(object)

    def __init__(self, theme, parent=None):
        super().__init__(parent)
        self.controller = CaptureController(self)
        self.displayed_snapshot = self.preview_snapshot = None
        self.theme = theme
        self.history = RecentSnapshots()
        self._build_ui()
        self.controller.state_changed.connect(self.task_label.setText)
        self.controller.progress.connect(self.progress.setValue)
        self.controller.completed.connect(self._completed)
        self.set_link_state({'connected': False})
        self._buttons()

    def _label(self, text):
        label = QLabel(text)
        label.setWordWrap(True)
        label.setTextFormat(Qt.PlainText)
        return label

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self.link_label = self._label('FPGA：未连接')
        connection_row = QHBoxLayout()
        connection_row.addWidget(self.link_label, 1)
        self.task_label = self._label('当前任务：就绪')
        connection_row.addWidget(self.task_label, 1)
        link_button = QPushButton('前往 FPGA 通信')
        link_button.clicked.connect(self.open_communication.emit)
        connection_row.addWidget(link_button)
        root.addLayout(connection_row)
        self.source_label = self._label('来源：电脑本地测试 · 硬件采集与输出待接入；本地数据不代表 ADC/DAC 验收。')
        root.addWidget(self.source_label)
        source_row = QHBoxLayout()
        source_row.addWidget(QLabel('下一次数据源'))
        self.source_combo = QComboBox()
        self.source_combo.addItems(['电脑本地测试', 'FPGA 板内数字源（非 ADC）', '真实 ADC（ATK-MO8008 V3.3）'])
        self.source_combo.setAccessibleName('下一次采集数据源')
        source_row.addWidget(self.source_combo, 1)
        root.addLayout(source_row)
        history_row = QHBoxLayout()
        self.import_button = QPushButton('打开数据包')
        self.import_button.clicked.connect(self._choose_import)
        history_row.addWidget(self.import_button)
        history_row.addWidget(QLabel('最近快照'))
        self.history_combo = QComboBox()
        self.history_combo.setMinimumWidth(0)
        self.history_combo.setAccessibleName('最近十份快照')
        self.history_combo.currentIndexChanged.connect(self._select_history)
        history_row.addWidget(self.history_combo, 1)
        root.addLayout(history_row)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setFrameShape(QScrollArea.NoFrame)
        body = QWidget()
        body.setObjectName('addaBody')
        body.setMinimumWidth(0)
        self.scroll_area.setWidget(body)
        for widget, name in [(self.scroll_area, 'addaScroll'),
                             (self.scroll_area.viewport(), 'addaViewport'), (body, 'addaBody')]:
            widget.setObjectName(name)
            widget.setStyleSheet('#' + name + ' { background-color: ' + self.theme['bg_app'] + '; }')
        content = QVBoxLayout(body)
        content.setContentsMargins(0, 0, 8, 0)
        content.setSpacing(12)
        self.digital_box = DigitalCaptureBox(self)
        self.digital_box.hide()
        self.digital_box.changed.connect(self._buttons)
        self.digital_box.message.connect(self.feedback_message)
        self.digital_box.snapshot_ready.connect(self._digital_complete)
        self.digital_box.partial_ready.connect(self._digital_partial)
        source_row.addWidget(self.digital_box.probe_button)
        self.digital_box.probe_button.hide()
        self.settings_widget = QWidget()
        self.settings_layout = QBoxLayout(QBoxLayout.LeftToRight, self.settings_widget)
        self.settings_layout.setContentsMargins(0, 0, 0, 0)
        self.adc_group = QGroupBox('数据与采集设置 · 本地单通道 / 8 bit')
        adc = QVBoxLayout(self.adc_group)
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.sample_rate = QDoubleSpinBox()
        self.sample_rate.setDecimals(3)
        self.sample_rate.setRange(1, 1e9)
        self.sample_rate.setValue(1e7)
        self.sample_rate.setSuffix(' Sa/s')
        self.sample_rate.setAccessibleName('配置采样率，非实测')
        self.count_combo = QComboBox()
        for count in (256, 1024, 4096):
            self.count_combo.addItem(str(count), count)
        self.count_combo.setCurrentIndex(2)
        self.count_combo.setAccessibleName('采样点数')
        form.addRow('配置采样率', self.sample_rate)
        form.addRow('采样点数', self.count_combo)
        adc.addLayout(form)
        self.adc_wave = WaveEditor()
        adc.addWidget(self.adc_wave)
        adc.addWidget(self._label('采样率仅用于本地计算时间轴；递增码每点加 1 并按 256 回绕。'))
        actions = QHBoxLayout()
        self.generate_button = QPushButton('生成本地数据')
        self.generate_button.setObjectName('primaryButton')
        self.generate_button.clicked.connect(self.generate)
        self.cancel_button = QPushButton('取消')
        self.cancel_button.clicked.connect(self.cancel_capture)
        actions.addWidget(self.generate_button)
        actions.addWidget(self.cancel_button)
        actions.addWidget(self.digital_box.release_button)
        self.digital_box.release_button.hide()
        self.settings_button = QPushButton('收起参数 / DAC 预览')
        self.settings_button.setCheckable(True)
        self.settings_button.setChecked(True)
        self.settings_button.toggled.connect(self._toggle_settings)
        actions.addWidget(self.settings_button)
        root.addLayout(actions)
        self.hardware_capture_button = QPushButton('真实 ADC 采集（待接入）')
        self.hardware_capture_button.setEnabled(False)
        adc.addWidget(self.hardware_capture_button)
        adc.addWidget(self._label('现有固件无 ADC 读取命令；连接板卡后也不会启用。'))
        adc.addStretch()
        self.dac_group = QGroupBox('DAC 数字波形预览 · 未提交设备')
        dac = QVBoxLayout(self.dac_group)
        self.dac_wave = WaveEditor(allow_ramp=False)
        dac.addWidget(self.dac_wave)
        self.preview_button = QPushButton('预览 DAC 数字波形')
        self.preview_button.clicked.connect(self.preview)
        dac.addWidget(self.preview_button)
        self.hardware_output_button = QPushButton('配置设备 / 启停（待接入）')
        self.hardware_output_button.setEnabled(False)
        dac.addWidget(self.hardware_output_button)
        dac.addWidget(self._label('预览使用左侧配置采样率与点数；与采集数据独立，不模拟 DAC→ADC 回环。'))
        self.preview_info = self._label('尚未生成预览；不会发送设备命令。')
        dac.addWidget(self.preview_info)
        self.preview_canvas = RawCanvas(self.theme, compact=True)
        dac.addWidget(self.preview_canvas)
        self.settings_layout.addWidget(self.adc_group, 1)
        self.settings_layout.addWidget(self.digital_box, 1)
        self.settings_layout.addWidget(self.dac_group, 1)
        content.addWidget(self.settings_widget)
        self.progress = QProgressBar()
        self.digital_box.progress.connect(self.progress.setValue)
        self.progress.setRange(0, 4096)
        self.progress.setValue(0)
        self.progress.setFormat('本次已生成 %v / %m 点')
        self.progress.hide()
        content.addWidget(self.progress)
        self.result_label = self._label('当前结果：暂无数据')
        self.result_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.views = SnapshotViews(self.theme)
        self.canvas, self.toolbar, self.axis_combo = self.views.canvas, self.views.toolbar, self.views.axis_combo
        self.views.tabs.currentChanged.connect(lambda: self._buttons())
        content.addWidget(self.views, 1)
        self.stats_label = self._label('点数 / 最小 / 最大 / 均值 / 总体标准差：—')
        content.addWidget(self.stats_label)
        self.check_label = self._label('完整性：尚无结果 · OTR / 捕获溢出：本地测试不适用')
        content.addWidget(self.check_label)
        content.addWidget(self.result_label)
        root.addWidget(self.scroll_area, 1)
        result_actions = QHBoxLayout()
        self.complete_button = QPushButton('最近完整结果')
        self.complete_button.clicked.connect(lambda: self._display(self.controller.current_snapshot))
        self.partial_button = QPushButton('本次部分数据')
        self.partial_button.clicked.connect(lambda: self._display(self.controller.last_partial))
        self.export_button = QPushButton('导出数据包')
        self.export_button.clicked.connect(self._choose_export)
        self.png_button = QPushButton('导出当前图 PNG')
        self.png_button.clicked.connect(self._choose_png)
        for button in (self.complete_button, self.partial_button, self.export_button, self.png_button):
            result_actions.addWidget(button)
        root.addLayout(result_actions)
        self.feedback = self._label('选择参数后点击“生成本地数据”；无需连接板卡。')
        root.addWidget(self.feedback)
        self.source_combo.currentIndexChanged.connect(self._source_changed)

    def bind_link(self, link):
        self.digital_box.bind_link(link)
        link.link_state_changed.connect(self.set_link_state)
        self.set_link_state(link.link_state())

    def feedback_message(self, text):
        self.feedback.setText(text)

    def _source_changed(self):
        board = self.source_combo.currentIndex() > 0
        self.digital_box.set_adc_mode(self.source_combo.currentIndex() == 2)
        self.digital_box.setVisible(board)
        self.digital_box.probe_button.setVisible(board)
        self.digital_box.release_button.setVisible(board)
        self.adc_group.setVisible(not board)
        self.generate_button.setText('采集真实 ADC' if self.source_combo.currentIndex() == 2 else ('采集板内数字源' if board else '生成本地数据'))
        if board:
            self.settings_button.setChecked(True)
        self._buttons()

    def cancel_capture(self):
        if self.digital_box.busy:
            self.digital_box.cancel()
            self.feedback.setText('正在取消读取，等待当前帧结束；不会释放板上缓存。')
        else:
            self.controller.cancel()

    def _digital_complete(self, snapshot):
        self.controller.current_snapshot = snapshot
        self._display(snapshot)
        self.task_label.setText('当前任务：{}完成 · {} 点'.format('真实 ADC ' if snapshot.source == 'FPGA_EXTERNAL_ADC' else '板内数字源', len(snapshot.samples)))

    def _digital_partial(self, snapshot):
        self.controller.last_partial = snapshot
        self.history.add(snapshot)
        self._sync_history()
        self.task_label.setText('当前任务：设备部分数据 · {} 点，未通过整段校验'.format(len(snapshot.samples)))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.settings_layout.setDirection(QBoxLayout.TopToBottom if self.width() < 840
                                          else QBoxLayout.LeftToRight)
        compact = self.height() < 650
        for index in (0, 1):
            self.views.tabs.widget(index).layout().setAlignment(Qt.AlignTop if compact else Qt.Alignment())
        self.source_label.setVisible(not compact)
        for canvas in (self.canvas, self.views.fft_canvas):
            canvas.setMinimumHeight(180 if compact else 220)
            canvas.setMaximumHeight(180 if compact else 16777215)

    def _toggle_settings(self, checked):
        self.settings_widget.setVisible(checked)
        self.digital_box.parameters.setVisible(checked)
        self.settings_button.setText('收起参数 / DAC 预览' if checked else '展开参数 / DAC 预览')

    def set_link_state(self, state):
        if not state.get('connected'):
            text = 'FPGA：未连接（本地测试可用）'
        else:
            text = 'FPGA：{} 通信在线 · 协议 {}{}'.format(
                state.get('port', ''), state.get('protocol', '未知'),
                ' · 发送已暂停' if state.get('sending_paused') else '')
        self.link_label.setText(text)

    def _config(self, editor):
        return CaptureConfig(self.count_combo.currentData(), self.sample_rate.value(), editor.config())

    def generate(self):
        if self.digital_box.busy or self.controller.busy or self.controller.closing:
            return
        if self.source_combo.currentIndex() > 0:
            self.progress.setRange(0, self.digital_box.count_combo.currentData())
            self.progress.setFormat('本次已读取 %v / %m 点')
            self.progress.setValue(0)
            self.progress.setVisible(self.digital_box.capture())
            self._buttons()
            return
        try:
            config = self._config(self.adc_wave)
            config.validate()
            self.progress.setRange(0, config.count)
            self.progress.setFormat('本次已生成 %v / %m 点')
            self.progress.show()
            if self.controller.start(config):
                self.feedback.setText('正在生成；旧结果仍保留。修改参数只影响下一次操作。')
        except ValueError as exc:
            self.feedback.setText('配置无效：' + str(exc))
        self._buttons()

    def preview(self):
        try:
            config = self._config(self.dac_wave)
            raw = b''.join(LocalTestSource().chunks(config, Event()))
            self.preview_snapshot = make_snapshot('DAC_LOCAL_PREVIEW', config, raw, 'complete')
            self.preview_canvas.render(self.preview_snapshot)
            self.preview_info.setText('仅本地预览：{} 点 · 配置 {} Sa/s · 未提交设备。'.format(
                config.count, format(config.sample_rate, 'g')))
            self.feedback.setText('DAC 预览已更新；当前采集快照未改变。')
        except ValueError as exc:
            self.feedback.setText('预览配置无效（上次预览保留）：' + str(exc))

    def _completed(self, report):
        self.progress.hide()
        status = {'complete': '完成', 'cancelled': '已取消', 'failed': '失败'}[report.status]
        self.task_label.setText('当前任务：{} · {} / {} 点'.format(
            status, report.actual_count, report.expected_count))
        if report.status == 'complete':
            self._display(self.controller.current_snapshot)
            self.settings_button.setChecked(False)
            self.scroll_area.verticalScrollBar().setValue(0)
            self.feedback.setText('本地生成完成；波形、统计与导出使用同一冻结快照。')
        else:
            if self.controller.last_partial is not None:
                self.history.add(self.controller.last_partial)
                self._sync_history()
            self.feedback.setText('{}。{} 当前显示结果保留；可重试{}。'.format(
                status, report.error, '或查看本次部分数据' if self.controller.last_partial else ''))
        self._buttons()

    def _display(self, snapshot):
        if snapshot is None:
            return
        self.displayed_snapshot = snapshot
        if not any(item.snapshot_id == snapshot.snapshot_id for item in self.history.items):
            self.history.add(snapshot)
        self._sync_history()
        self.settings_button.setChecked(False)
        source = self.source_text(snapshot)
        self.source_label.setText('当前来源：' + source + ' · 本页 DAC 仅作预览；RF 控制见文本收发页。')
        config = snapshot.config
        self.result_label.setText('当前结果：{} · {} · {}\n快照 {} · {} 点 · 配置 {} Sa/s'.format(
            '完整' if snapshot.status == 'complete' else '部分（非整段通过）', source, snapshot.created_at,
            snapshot.snapshot_id, len(snapshot.samples), format(config.sample_rate, 'g')))
        self.result_label.setText(self.result_label.text() + '\n波形 {} · 频率 {} Hz · 峰值幅度 {} code · 固定码/偏置 {} code'.format(
            {'sine': '正弦', 'fixed': '固定码', 'ramp': '递增码', 'walking': 'Walking 单比特码', 'external_adc': '真实 ADC 原始码'}[config.wave.kind],
            format(config.wave.frequency, 'g') if config.wave.kind == 'sine' else '不适用',
            config.wave.amplitude if config.wave.kind == 'sine' else '不适用',
            config.wave.offset if config.wave.kind != 'ramp' else '不适用'))
        stats = statistics(snapshot)
        self.stats_label.setText('点数 {count} · 最小 {minimum} · 最大 {maximum} · 均值 {mean:.4f} · '
                                 '总体标准差 {std_population:.4f} code'.format(**stats))
        self.check_label.setText('完整性：{} / {} 点，原始码范围检查通过；{}。OTR / 溢出：不适用。'.format(
            len(snapshot.samples), config.count,
            '本地完整数据' if snapshot.status == 'complete' else '部分数据，不记整段通过'))
        if snapshot.digital_info:
            info = snapshot.digital_info
            self.result_label.setText(self.result_label.text() + '\n会话 {:08X} · 采集 {} · 标称 {} MSa/s，非实测。'.format(info.session, info.capture_id, config.sample_rate/1e6))
            self.check_label.setText('CRC32：{} · {} / {} 点；OTR / 溢出：未统计。'.format(
                ('文件声明一致，非本次硬件验证' if snapshot.import_info else '整段通过') if info.verified else '未通过整段校验（部分数据）',
                len(snapshot.samples), config.count))
        self.views.set_snapshot(snapshot)
        self.selection_changed.emit(snapshot)
        self._buttons()

    def _redraw(self):
        self.views.redraw_time()

    @staticmethod
    def source_text(snapshot):
        origin = snapshot.import_info.declared_source if snapshot and snapshot.import_info else getattr(snapshot, 'source', '')
        label = {'FPGA_INTERNAL_DIGITAL_TEST': 'FPGA 板内数字源（非 ADC）', 'FPGA_EXTERNAL_ADC': '真实 ADC（8 bit 原始码，未校准）'}.get(origin, '电脑本地测试')
        return ('文件导入（原始来源声明：' + label + '；非本次硬件验证）'
                if snapshot and snapshot.import_info else label)

    def _sync_history(self):
        self.history_combo.blockSignals(True)
        self.history_combo.clear()
        for item in self.history.items:
            self.history_combo.addItem('{} · {} · {} · {} 点 · {}'.format(
                '导入' if item.import_info else ('ADC' if item.source == 'FPGA_EXTERNAL_ADC' else ('板内' if item.digital_info else '本地')), item.created_at,
                '完整' if item.status == 'complete' else '部分', len(item.samples), item.snapshot_id[:8]), item.snapshot_id)
        if self.displayed_snapshot:
            self.history_combo.setCurrentIndex(self.history_combo.findData(self.displayed_snapshot.snapshot_id))
        self.history_combo.blockSignals(False)

    def _select_history(self, index):
        identity = self.history_combo.itemData(index)
        for item in self.history.items:
            if item.snapshot_id == identity:
                self._display(item)
                self.feedback.setText('已切换历史快照；输入框仍是下一次生成的参数。')
                break

    def _choose_import(self):
        entry, _ = QFileDialog.getOpenFileName(self, '打开数据包中的任意一个文件（三份文件须在同一目录）',
                                              '', 'AD/DA 数据包 (*.json *.bin *.csv)')
        if entry:
            self.import_from(entry)

    def import_from(self, entry):
        if self.controller.busy or self.controller.closing or self.digital_box.busy:
            self.feedback.setText('请先等待当前任务完成或取消，再导入。')
            return False
        try:
            snapshot = import_package(entry)
            self._display(snapshot)
            self.task_label.setText('当前任务：数据包导入完成 · {} 点'.format(len(snapshot.samples)))
            self.feedback.setText('三文件一致性校验通过；已作为文件导入快照打开，来源声明不代表硬件验收。')
            return True
        except ValueError as exc:
            self.feedback.setText(str(exc) + '；当前结果保留，请检查三份配套文件。')
            return False

    def _buttons(self):
        if not hasattr(self, 'png_button'):
            return
        busy = self.controller.busy or self.controller.closing or self.digital_box.busy
        self.generate_button.setEnabled(not busy and (self.source_combo.currentIndex() == 0 or self.digital_box.can_capture))
        self.source_combo.setEnabled(not busy)
        self.cancel_button.setEnabled((self.controller.busy or self.digital_box.capturing) and not self.controller.closing)
        if not self.digital_box.busy and not self.controller.busy:
            self.progress.hide()
        self.digital_box.setEnabled(not self.controller.busy and not self.controller.closing)
        self.complete_button.setEnabled(self.controller.current_snapshot is not None)
        self.partial_button.setEnabled(self.controller.last_partial is not None and not busy)
        self.export_button.setEnabled(self.displayed_snapshot is not None)
        self.import_button.setEnabled(not busy)
        self.history_combo.setEnabled(not busy and bool(self.history.items))
        can_plot = self.views.tabs.currentIndex() in (0, 1) and self.displayed_snapshot is not None
        if self.views.tabs.currentIndex() == 1 and self.displayed_snapshot is not None:
            can_plot = len(self.displayed_snapshot.samples) >= 2
        self.png_button.setEnabled(can_plot and not self.controller.closing)

    def _image_options(self):
        return dict(mode='time' if self.views.tabs.currentIndex() == 0 else 'spectrum',
                    time_axis=self.axis_combo.currentIndex() == 1,
                    window=self.views.window_combo.currentData(), remove_dc=self.views.remove_dc.isChecked())

    def _choose_png(self):
        snapshot, options = self.displayed_snapshot, self._image_options()
        path, _ = QFileDialog.getSaveFileName(self, '导出当前图类型的完整快照（不裁剪缩放视区）', '', 'PNG 图片 (*.png)')
        if path:
            self.save_image(path if path.lower().endswith('.png') else path + '.png', snapshot, options)

    def save_image(self, path, snapshot=None, options=None):
        snapshot = snapshot if snapshot is not None else self.displayed_snapshot
        if snapshot is None or (options is None and self.views.tabs.currentIndex() == 2):
            self.feedback.setText('请先选择有数据的时域或频谱视图。')
            return None
        try:
            result = export_png(snapshot, path, **(options or self._image_options()))
            self.feedback.setText('已导出完整快照图片（来源、状态与配置附在图中）：' + str(result))
            return result
        except Exception as exc:
            self.feedback.setText('图片导出失败，当前结果保留：' + str(exc))
            return None

    def _choose_export(self):
        snapshot = self.displayed_snapshot
        parent = QFileDialog.getExistingDirectory(self, '选择数据包保存目录（创建独立子文件夹）')
        if parent:
            self.export_to(parent, snapshot)

    def export_to(self, parent, snapshot=None):
        snapshot = snapshot if snapshot is not None else self.displayed_snapshot
        if snapshot is None:
            self.feedback.setText('暂无可导出的采集结果；DAC 预览不作为采集数据导出。')
            return None
        try:
            target = export_snapshot(snapshot, parent)
            self.feedback.setText('已导出当前{}快照：{}'.format(
                '完整' if snapshot.status == 'complete' else '部分', target))
            return target
        except Exception as exc:
            self.feedback.setText('导出失败，内存结果保留；请换目录后重试：' + str(exc))
            return None

    def shutdown(self):
        self.digital_box.shutdown()
        self.controller.shutdown()
        self.views.shutdown()
        self.preview_canvas.shutdown()
        self._buttons()
