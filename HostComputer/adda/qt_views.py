from PyQt5.QtCore import Qt, QAbstractTableModel, QModelIndex
from PyQt5.QtWidgets import (QWidget, QTabWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QComboBox, QCheckBox, QTableView, QSpinBox, QPushButton,
                             QAbstractItemView, QHeaderView)
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT

from .qt_widgets import RawCanvas


def navigation_toolbar(canvas, parent, theme):
    toolbar = NavigationToolbar2QT(canvas, parent, coordinates=False)
    for action in list(toolbar.actions()):
        if action.text() in ('Subplots', 'Customize', 'Save'):
            toolbar.removeAction(action)
    toolbar.setToolButtonStyle(Qt.ToolButtonTextOnly)
    for name, text in [('home', '恢复视图'), ('back', '上个视图'), ('forward', '下个视图'),
                       ('pan', '平移'), ('zoom', '缩放')]:
        toolbar._actions[name].setText(text)
    toolbar.setStyleSheet('QToolBar { background: ' + theme['bg_app'] + '; border: none; } '
                         'QToolButton { color: ' + theme['text_primary'] + '; padding: 4px; } '
                         'QToolButton:checked { background: ' + theme['bg_selected'] + '; }')
    return toolbar


class RawCodeModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.snapshot = None

    def set_snapshot(self, snapshot):
        self.beginResetModel()
        self.snapshot = snapshot
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() or self.snapshot is None else len(self.snapshot.samples)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else 4

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole:
            return (['样本序号', '时间 / s（按配置）', '原始码（十进制）', '原始码（十六进制）'][section]
                    if orientation == Qt.Horizontal else str(section))

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or self.snapshot is None:
            return None
        if role == Qt.TextAlignmentRole:
            return int(Qt.AlignRight | Qt.AlignVCenter)
        if role == Qt.DisplayRole:
            row = index.row()
            code = int(self.snapshot.samples[row])
            return [str(row), format(row / self.snapshot.config.sample_rate, '.12g'),
                    str(code), '0x{:02X}'.format(code)][index.column()]


class SnapshotViews(QWidget):
    def __init__(self, theme, parent=None):
        super().__init__(parent)
        self.snapshot = None
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self.tabs = QTabWidget()
        self.tabs.setObjectName('addaViews')
        self.tabs.setStyleSheet('QTabWidget::pane { border: 1px solid ' + theme['border_subtle'] + '; } '
                               'QTabBar::tab { background: ' + theme['bg_panel'] + '; color: ' + theme['text_primary'] + '; padding: 6px 14px; } '
                               'QTabBar::tab:selected { background: ' + theme['bg_selected'] + '; } '
                               'QTabBar::tab:focus { border: 1px solid ' + theme['border_focus'] + '; }')
        root.addWidget(self.tabs)
        time_page = QWidget()
        time_layout = QVBoxLayout(time_page)
        time_layout.setContentsMargins(6, 4, 6, 4)
        time_layout.setSpacing(4)
        self.axis_combo = QComboBox()
        self.axis_combo.addItems(['样本序号', '时间（按配置采样率）'])
        self.axis_combo.setAccessibleName('时域横轴')
        self.axis_combo.currentIndexChanged.connect(self.redraw_time)
        time_layout.addWidget(self.axis_combo)
        self.canvas = RawCanvas(theme)
        self.toolbar = navigation_toolbar(self.canvas, self, theme)
        time_layout.addWidget(self.toolbar)
        time_layout.addWidget(self.canvas, 1)
        self.tabs.addTab(time_page, '时域波形')
        spectrum_page = QWidget()
        fft_layout = QVBoxLayout(spectrum_page)
        fft_layout.setContentsMargins(6, 4, 6, 4)
        fft_layout.setSpacing(4)
        controls = QHBoxLayout()
        self.window_combo = QComboBox()
        self.window_combo.addItem('Hann 窗', 'hann')
        self.window_combo.addItem('矩形窗', 'rectangular')
        self.window_combo.setAccessibleName('频谱窗函数')
        controls.addWidget(self.window_combo)
        self.remove_dc = QCheckBox('去除直流')
        self.remove_dc.setChecked(True)
        controls.addWidget(self.remove_dc)
        controls.addStretch()
        fft_layout.addLayout(controls)
        self.fft_canvas = RawCanvas(theme)
        self.fft_toolbar = navigation_toolbar(self.fft_canvas, self, theme)
        fft_layout.addWidget(self.fft_toolbar)
        fft_layout.addWidget(self.fft_canvas, 1)
        self.spectrum_label = QLabel('暂无频谱数据')
        self.spectrum_label.setWordWrap(True)
        self.spectrum_label.setTextFormat(Qt.PlainText)
        root.addWidget(self.spectrum_label)
        self.spectrum_label.hide()
        self.tabs.currentChanged.connect(lambda index: self.spectrum_label.setVisible(index == 1))
        self.tabs.addTab(spectrum_page, 'FFT 频谱')
        self.window_combo.currentIndexChanged.connect(self.redraw_spectrum)
        self.remove_dc.toggled.connect(self.redraw_spectrum)
        table_page = QWidget()
        table_layout = QVBoxLayout(table_page)
        table_layout.setContentsMargins(6, 4, 6, 4)
        table_layout.setSpacing(4)
        jump_row = QHBoxLayout()
        jump_row.addWidget(QLabel('定位样本序号'))
        self.jump_index = QSpinBox()
        self.jump_index.setRange(0, 0)
        self.jump_index.setAccessibleName('要定位的样本序号')
        jump_row.addWidget(self.jump_index)
        self.jump_button = QPushButton('定位')
        self.jump_button.clicked.connect(self._jump)
        jump_row.addWidget(self.jump_button)
        jump_row.addStretch()
        table_layout.addLayout(jump_row)
        self.table = QTableView()
        self.table.setAccessibleName('冻结快照原始码表格，只读')
        self.table.setStyleSheet('QTableView { background: ' + theme['bg_input'] + '; color: ' + theme['text_primary'] +
                                '; gridline-color: ' + theme['border_subtle'] + '; selection-background-color: ' +
                                theme['bg_selected'] + '; selection-color: ' + theme['text_primary'] + '; } '
                                'QHeaderView::section, QTableCornerButton::section { background: ' + theme['bg_panel'] +
                                '; color: ' + theme['text_primary'] + '; border: 1px solid ' + theme['border_subtle'] + '; padding: 6px; } '
                                'QTableView:focus { border: 1px solid ' + theme['border_focus'] + '; }')
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setMinimumHeight(200)
        self.model = RawCodeModel(self)
        self.table.setModel(self.model)
        table_layout.addWidget(self.table)
        self.tabs.addTab(table_page, '原始码表格')

    def set_snapshot(self, snapshot):
        self.snapshot = snapshot
        self.redraw_time()
        self.redraw_spectrum()
        self.model.set_snapshot(snapshot)
        self.jump_index.setRange(0, max(0, len(snapshot.samples) - 1))

    def redraw_time(self):
        self.canvas.render(self.snapshot, self.axis_combo.currentIndex() == 1)
        self.toolbar.update()

    def redraw_spectrum(self):
        result = self.fft_canvas.render_spectrum(self.snapshot, self.window_combo.currentData(), self.remove_dc.isChecked())
        self.fft_toolbar.update()
        if result is None:
            text = '频谱至少需要 2 个样本；频率轴按配置采样率计算。'
        else:
            peak = '无非零频谱分量' if result['peak_frequency'] is None else '主峰 {:.6g} Hz · 幅度 {:.6g} code'.format(
                result['peak_frequency'], result['peak_amplitude'])
            text = peak + ' · bin 间隔 {:.6g} Hz；单边峰值幅度，已补偿窗增益，非功率谱。'.format(result['bin_width'])
        self.spectrum_label.setText(text)

    def _jump(self):
        if self.model.rowCount():
            index = self.model.index(self.jump_index.value(), 0)
            self.table.setCurrentIndex(index)
            self.table.scrollTo(index, QAbstractItemView.PositionAtCenter)

    def shutdown(self):
        self.canvas.shutdown()
        self.fft_canvas.shutdown()
