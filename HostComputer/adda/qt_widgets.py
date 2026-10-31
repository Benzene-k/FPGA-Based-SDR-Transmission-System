from PyQt5.QtWidgets import (QWidget, QFormLayout, QComboBox, QSpinBox,
                             QDoubleSpinBox, QSizePolicy)
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
from matplotlib.figure import Figure
import numpy as np

from .models import WaveConfig


class WaveEditor(QWidget):
    def __init__(self, allow_ramp=True, parent=None):
        super().__init__(parent)
        form = QFormLayout(self)
        form.setContentsMargins(0, 0, 0, 0)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.kind = QComboBox()
        self.kind.addItem('正弦', 'sine')
        self.kind.addItem('固定码', 'fixed')
        if allow_ramp:
            self.kind.addItem('递增码 0～255', 'ramp')
        self.frequency = QDoubleSpinBox()
        self.frequency.setRange(0.001, 1e9)
        self.frequency.setDecimals(3)
        self.frequency.setValue(39062.5)
        self.frequency.setSuffix(' Hz')
        self.amplitude = QSpinBox()
        self.amplitude.setRange(0, 255)
        self.amplitude.setValue(32)
        self.amplitude.setSuffix(' code')
        self.offset = QSpinBox()
        self.offset.setRange(0, 255)
        self.offset.setValue(128)
        self.offset.setSuffix(' code')
        for text, widget in [('测试波形', self.kind), ('配置频率', self.frequency),
                             ('数字峰值幅度', self.amplitude), ('固定码 / 偏置', self.offset)]:
            widget.setAccessibleName(text)
            widget.setMinimumWidth(140)
            form.addRow(text, widget)
        self.kind.currentIndexChanged.connect(self._availability)
        self._availability()

    def _availability(self):
        sine = self.kind.currentData() == 'sine'
        self.frequency.setEnabled(sine)
        self.amplitude.setEnabled(sine)
        self.offset.setEnabled(self.kind.currentData() != 'ramp')

    def config(self):
        return WaveConfig(self.kind.currentData(), self.frequency.value(),
                          self.amplitude.value(), self.offset.value())


class RawCanvas(FigureCanvasQTAgg):
    def __init__(self, theme, compact=False):
        self.theme = theme
        self._closed = False
        figure = Figure(figsize=(7, 2 if compact else 3.5), constrained_layout=True)
        super().__init__(figure)
        self.axes = figure.subplots()
        self.figure.patch.set_facecolor(theme['bg_app'])
        self.setMinimumHeight(170 if compact else 220)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.render(None)

    def draw_idle(self):
        if not self._closed:
            super().draw_idle()

    def shutdown(self):
        self._closed = True
        self._draw_pending = False

    def render(self, snapshot, time_axis=False):
        self._prepare_axes()
        ax = self.axes
        ax.set_ylim(-5, 260)
        ax.set_ylabel('原始码 / code', color=self.theme['text_primary'])
        ax.set_xlabel('时间 / μs（按配置采样率计算）' if time_axis else '样本序号',
                      color=self.theme['text_primary'])
        if snapshot is None:
            ax.text(0.5, 0.5, '暂无数据', transform=ax.transAxes, ha='center',
                    color=self.theme['text_secondary'])
        else:
            x = np.arange(len(snapshot.samples))
            if time_axis:
                x = x / snapshot.config.sample_rate * 1e6
            ax.plot(x, snapshot.samples, color=self.theme['chart_rx'], linewidth=1)
            if len(x) > 1:
                ax.set_xlim(float(x[0]), float(x[-1]))
        self.draw_idle()

    def _prepare_axes(self):
        ax = self.axes
        ax.clear()
        ax.set_facecolor(self.theme['bg_input'])
        ax.tick_params(colors=self.theme['text_secondary'], labelsize=11)
        for spine in ax.spines.values():
            spine.set_color(self.theme['border_subtle'])
        ax.grid(color=self.theme['divider'], alpha=0.6)

    def render_spectrum(self, snapshot, window='hann', remove_dc=True):
        from .analysis import spectrum
        self._prepare_axes()
        ax = self.axes
        ax.set_xlabel('频率 / Hz（按配置采样率计算）', color=self.theme['text_primary'])
        ax.set_ylabel('单边峰值幅度 / code', color=self.theme['text_primary'])
        result = None
        if snapshot is None or len(snapshot.samples) < 2:
            ax.text(0.5, 0.5, '暂无数据或不足 2 点', transform=ax.transAxes,
                    ha='center', color=self.theme['text_secondary'])
        else:
            result = spectrum(snapshot, window, remove_dc)
            ax.plot(result['frequency'], result['amplitude'], color=self.theme['chart_spectrum'], linewidth=1)
            ax.set_xlim(0, snapshot.config.sample_rate / 2)
            ax.set_ylim(bottom=0)
        self.draw_idle()
        return result
