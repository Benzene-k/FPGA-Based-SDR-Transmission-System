
import csv
import json
import math
import os
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from time import monotonic
from uuid import uuid4
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
from matplotlib import rcParams
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QFont
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QSplitter,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.ticker import AutoMinorLocator, MaxNLocator


rcParams["font.family"] = "sans-serif"
rcParams["font.sans-serif"] = [
    "Microsoft YaHei UI",
    "Microsoft YaHei",
    "SimHei",
    "SimSun",
    "DejaVu Sans",
]
rcParams["font.size"] = 12
rcParams["axes.unicode_minus"] = False


APP_TITLE = "Chirp 通信演示上位机 V0.11 实验可靠性版"
APP_VERSION = "0.11.0"
UI_FONT_FAMILY = "Microsoft YaHei UI"
UI_FONT_FALLBACK = '"Microsoft YaHei UI", "Microsoft YaHei", "SimHei"'
PRESET_FILE = Path(__file__).with_name("chirp_user_presets.json")
SESSION_ROOT = Path(__file__).with_name("experiment_sessions")
BUILT_IN_PRESETS = {
    "理想信道": {
        "channel_mode": "仅AWGN",
        "snr_db": 30.0,
        "nakagami_m": 1.0,
        "attenuation_db": 0.0,
    },
    "低噪声": {
        "channel_mode": "Nakagami多径 + AWGN",
        "snr_db": 20.0,
        "nakagami_m": 2.0,
        "attenuation_db": 0.0,
    },
    "强噪声": {
        "channel_mode": "Nakagami多径 + AWGN",
        "snr_db": 0.0,
        "nakagami_m": 1.0,
        "attenuation_db": 0.0,
    },
    "严重衰落": {
        "channel_mode": "Nakagami多径 + AWGN",
        "snr_db": 8.0,
        "nakagami_m": 0.5,
        "attenuation_db": 6.0,
    },
}

TERM_GLOSSARY = {
    "射频（RF）": ("Radio Frequency，射频。通常指用于无线发射和接收的高频电磁信号。", "项目与设备语境"),
    "Chirp": ("一种频率随时间连续上升或下降的扫频信号。本程序用正、负斜率的Chirp波形演示数据传输。", "调制与波形"),
    "Binary Chirp": ("二进制Chirp调制：用两种不同的Chirp信号状态表示0和1。本程序当前用于界面流程演示。", "调制方式"),
    "BPSK": ("Binary Phase Shift Keying，二进制相移键控，用两个载波相位状态表示0和1；当前界面仅预留选项。", "预留调制方式"),
    "QPSK": ("Quadrature Phase Shift Keying，四相相移键控，用四个载波相位状态表示数据；当前界面仅预留选项。", "预留调制方式"),
    "调制": ("把待发送的数据映射到载波或信号特征上的过程；本程序当前演示Binary Chirp调制。", "收发流程"),
    "解调": ("接收端从信号中判断并恢复发送数据的过程。", "收发流程"),
    "信道": ("信号从发送端到接收端经过的传播环境；可包含噪声、衰落和衰减。", "信道模型"),
    "信噪比（SNR）": ("Signal-to-Noise Ratio，信号功率与噪声功率之比，通常以dB表示。数值越高通常表示噪声相对越弱。", "常用参数"),
    "误比特率（BER）": ("Bit Error Rate，错误比特数除以比较的总比特数。本程序显示值来自模拟后端，不代表实际无线链路测量。", "统计指标"),
    "AWGN": ("Additive White Gaussian Noise，加性白高斯噪声，是常见的理想化噪声模型。", "信道模型"),
    "Nakagami衰落": ("一种描述无线信号幅度起伏的统计模型；m参数控制衰落分布形态。本程序仅作简化模拟。", "信道模型"),
    "衰减": ("信号功率或幅度在传输中减小的量，界面参数以dB表示；模拟中用于降低接收信号的有效信噪比。", "信道参数"),
    "比特（bit）": ("二进制信息的基本单位，只能取0或1。", "数据与统计"),
    "字节（Byte）": ("通常由8个比特组成的数据单位。字节数描述数据量，不等同于无线有效吞吐率。", "数据与统计"),
    "帧": ("为一次处理而组织的一组数据，通常包含同步信息和数据内容。帧数是处理单元数量，不是字节数。", "数据与统计"),
    "净荷": ("帧中承载的实际用户数据部分，不包含用于同步或控制的开销。", "数据成帧"),
    "同步头": ("放在数据帧开头、供接收端定位帧边界使用的已知序列。", "帧同步"),
    "帧同步": ("接收端在连续采样数据中定位帧起点的过程；同步头可帮助估计帧边界。", "收发流程"),
    "采样率": ("每秒对连续信号取样的次数，单位通常为samples/s或MHz；必须与带宽等参数匹配。", "高级参数"),
    "带宽": ("信号占用的频率范围宽度，单位Hz或MHz。界面中的Chirp带宽是扫频跨度。", "高级参数"),
    "Chirp时长": ("单个Chirp波形持续的时间；它和采样率共同决定用于表示波形的采样点数。", "高级参数"),
    "时域": ("以时间为横轴观察信号变化的表示方式。", "图表"),
    "频域": ("以频率为横轴观察信号能量分布的表示方式。", "图表"),
    "频谱": ("信号在不同频率上的幅度或功率分布。本程序图表显示归一化幅度。", "图表"),
    "FFT": ("Fast Fourier Transform，快速傅里叶变换，用于将离散信号从时域转换到频域。", "信号处理"),
    "正交解调（Dechirp）": ("通过与参考Chirp信号混频等方式降低扫频信号复杂度的处理方法；本程序当前为流程界面演示。", "信号处理"),
    "多普勒": ("收发端相对运动导致接收信号频率发生偏移的现象。当前版本参数为界面预留。", "高级参数"),
    "随机种子": ("伪随机数生成器的初始值；使用相同种子和相同流程有助于复现模拟结果。", "模拟参数"),
    "模拟后端": ("用软件生成示例收发数据和统计结果的演示实现；不调用真实HackRF、FPGA或射频信道。", "当前版本边界"),
    "MATLAB": ("用于数值计算和仿真的软件。本程序顶部的MATLAB状态表示接口预留状态，不代表已连接。", "接口状态"),
    "FPGA": ("Field-Programmable Gate Array，现场可编程门阵列，可用于实现高速数字信号处理。当前版本接口待接入。", "接口状态"),
    "HackRF": ("可编程软件无线电硬件平台，可用于实际射频收发实验；当前V0.11仍使用模拟后端。", "实验硬件"),
    "吞吐率": ("单位时间内成功传输的有效数据量。程序运行速度、理论信号时长或正确比特折算字节数都不能单独证明实际无线吞吐率。", "统计指标"),
    "dB": ("分贝，用对数方式表示功率比或增益、衰减等比例关系的单位。", "单位"),
}

PAGE_TERM_KEYS = {
    "系统总览": ["Chirp", "调制", "解调", "信道", "信噪比（SNR）", "误比特率（BER）", "AWGN", "Nakagami衰落", "帧", "同步头", "帧同步", "FFT", "正交解调（Dechirp）"],
    "收发控制": ["Chirp", "Binary Chirp", "BPSK", "QPSK", "调制", "信道", "信噪比（SNR）", "AWGN", "Nakagami衰落", "衰减", "字节（Byte）", "比特（bit）", "帧", "净荷", "同步头", "采样率", "带宽", "Chirp时长", "多普勒", "随机种子", "dB"],
    "实时监视": ["时域", "比特（bit）", "误比特率（BER）", "帧", "字节（Byte）", "模拟后端"],
    "性能分析": ["时域", "频域", "频谱", "FFT", "误比特率（BER）", "模拟后端", "吞吐率"],
    "实验记录": ["信噪比（SNR）", "比特（bit）", "误比特率（BER）", "帧", "吞吐率"],
    "系统日志": ["MATLAB", "FPGA", "模拟后端", "HackRF"],
}


THEME = {
    "bg_app": "#0A0F14",
    "bg_sidebar": "#101923",
    "bg_toolbar": "#0E161D",
    "bg_panel": "#101A22",
    "bg_panel_raised": "#13202A",
    "bg_input": "#0B131A",
    "bg_hover": "#16242E",
    "bg_selected": "#173044",
    "border_subtle": "#21323E",
    "border_strong": "#314A5B",
    "border_focus": "#3A9BD6",
    "divider": "#1C2A34",
    "text_primary": "#DEE7EE",
    "text_secondary": "#9AAAB6",
    "text_disabled": "#62717C",
    "text_on_accent": "#F5F9FC",
    "accent": "#2EA8FF",
    "accent_hover": "#45B4FF",
    "accent_pressed": "#2189CF",
    "accent_soft": "#236A98",
    "success": "#46D39A",
    "warning": "#E0AD4F",
    "danger": "#FF7080",
    "chart_tx": "#4CA6D8",
    "chart_rx": "#59B79B",
    "chart_spectrum": "#C4A35A",
    "chart_ber": "#AAB8C3",
}

UI_METRICS = {
    "space_4": 4,
    "space_8": 8,
    "space_12": 12,
    "space_16": 16,
    "space_24": 24,
    "space_32": 32,
    "radius_input": 4,
    "radius_button": 5,
    "radius_panel": 7,
    "control_height": 32,
    "sidebar_width": 210,
}

THEME.update({
    "bg_app": "#080E1A", "bg_sidebar": "#101A2B", "bg_toolbar": "#0A1423",
    "bg_panel": "#101A2B", "bg_panel_raised": "#17263B", "bg_input": "#0A1423",
    "bg_hover": "#1D3D65", "bg_selected": "#193B67",
    "border_subtle": "#263B55", "border_strong": "#49617F", "border_focus": "#59DFFF",
    "divider": "#263B55", "text_primary": "#EAF3FF", "text_secondary": "#A7B9D0",
    "text_disabled": "#7A8DA7", "accent": "#59DFFF", "accent_hover": "#3475E7",
    "accent_pressed": "#1D50B3", "accent_soft": "#193B67",
    "success": "#5FE0AE", "warning": "#FFCA72", "danger": "#FF9BAD",
    "chart_tx": "#659AFF", "chart_rx": "#59DFFF", "chart_spectrum": "#FFCA72",
    "chart_ber": "#9DB5FF",
})
THEME.update(
    {
        "bg_main": THEME["bg_app"],
        "bg_topbar": THEME["bg_toolbar"],
        "bg_card": THEME["bg_panel"],
        "bg_card_alt": THEME["bg_panel_raised"],
        "border": THEME["border_strong"],
        "border_soft": THEME["border_subtle"],
        "accent_muted": THEME["accent_soft"],
    }
)


@dataclass
class ExperimentConfig:

    work_mode: str = "模拟模式"
    modulation: str = "Binary Chirp（正/负斜率）"
    source_coding: str = "当前单一编码"
    channel_mode: str = "Nakagami多径 + AWGN"
    snr_db: float = 15.0
    sample_rate_mhz: float = 56.0
    bandwidth_mhz: float = 7.0
    chirp_duration_us: float = 10.0
    frame_length: int = 30
    sync_length: int = 13
    guard_percent: float = 20.0
    nakagami_m: float = 0.5
    attenuation_db: float = 0.0
    random_seed: int = 20260919


@dataclass
class ExperimentStats:

    tx_bits: int = 0
    rx_bits: int = 0
    error_bits: int = 0
    total_frames: int = 0
    processed_frames: int = 0
    correct_frames: int = 0
    error_frames: int = 0
    lost_frames: int = 0
    unprocessed_frames: int = 0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    elapsed_seconds: float = 0.0

    @property
    def ber(self) -> float:
        return self.error_bits / self.rx_bits if self.rx_bits else 0.0


class BackendInterface:

    name = "Backend"

    def connect(self) -> None:
        raise NotImplementedError

    def disconnect(self) -> None:
        raise NotImplementedError

    def configure(self, config: ExperimentConfig) -> None:
        raise NotImplementedError

    def start(self, payload: bytes) -> None:
        raise NotImplementedError

    def stop(self) -> None:
        raise NotImplementedError


class MatlabAdapter(BackendInterface):

    name = "MATLAB Engine（待接入）"

    def connect(self) -> None:
        raise NotImplementedError("等待 MATLAB 函数输入输出接口确定")


class FpgaAdapter(BackendInterface):

    name = "FPGA（待接入）"

    def connect(self) -> None:
        raise NotImplementedError("等待 FPGA 通信协议确定")


class MetricCard(QFrame):

    def __init__(
        self,
        title: str,
        value: str,
        color: str = THEME["text_primary"],
        unit: str = "",
    ) -> None:
        super().__init__()
        self.setObjectName("metricCard")
        self.setMinimumHeight(100)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.unit = unit
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 12, 6, 12)
        layout.setSpacing(UI_METRICS["space_8"])
        title_label = QLabel(title)
        title_label.setObjectName("cardTitle")
        value_row = QHBoxLayout()
        value_row.setContentsMargins(0, 0, 0, 0)
        value_row.setSpacing(UI_METRICS["space_4"])
        self.value_label = QLabel()
        self.value_label.setObjectName("cardValue")
        self.value_label.setStyleSheet("color: {};".format(color))
        self.unit_label = QLabel(unit)
        self.unit_label.setObjectName("cardUnit")
        self.unit_label.setVisible(bool(unit))
        value_row.addWidget(self.value_label)
        value_row.addWidget(self.unit_label)
        value_row.addStretch(1)
        layout.addWidget(title_label)
        layout.addLayout(value_row)
        self.set_value(value)

    def set_value(self, value: str) -> None:
        display_value = value.strip()
        if self.unit and display_value.endswith(self.unit):
            display_value = display_value[: -len(self.unit)].strip()
        self.value_label.setText(display_value)
        self.setAccessibleName("{} {} {}".format(self.findChild(QLabel, "cardTitle").text(), display_value, self.unit).strip())


class StatusPill(QFrame):

    COLORS = {
        "idle": THEME["text_disabled"],
        "working": THEME["accent"],
        "ok": THEME["success"],
        "warning": THEME["warning"],
        "error": THEME["danger"],
    }

    def __init__(self, name: str, value: str = "待接入") -> None:
        super().__init__()
        self.setObjectName("statusPill")
        row = QHBoxLayout(self)
        row.setContentsMargins(9, 4, 10, 4)
        row.setSpacing(6)
        self.dot = QLabel("●")
        self.name_label = QLabel(name)
        self.name_label.setObjectName("statusName")
        self.value_label = QLabel(value)
        self.value_label.setObjectName("statusValue")
        row.addWidget(self.dot)
        row.addWidget(self.name_label)
        row.addWidget(self.value_label)
        self.set_status(value, "idle")

    def set_status(self, value: str, state: str = "idle") -> None:
        self.value_label.setText(value)
        self.dot.setStyleSheet("color: {};".format(self.COLORS.get(state, self.COLORS["idle"])))


class FlowNode(QFrame):

    def __init__(self, number: str, title: str, subtitle: str) -> None:
        super().__init__()
        self.setObjectName("flowNode")
        self.setProperty("state", "idle")
        self.setMinimumWidth(0)
        self.setMinimumHeight(104)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        column = QVBoxLayout(self)
        pad_x = 6
        pad_y = 6
        column.setContentsMargins(pad_x, pad_y, pad_x, pad_y)
        column.setSpacing(3)
        self.number_label = QLabel(number)
        self.number_label.setObjectName("flowNumber")
        self.title_label = QLabel(title)
        self.title_label.setObjectName("flowTitle")
        self.title_label.setWordWrap(True)
        self.subtitle_label = QLabel(subtitle)
        self.subtitle_label.setObjectName("flowSubtitle")
        self.subtitle_label.setWordWrap(True)
        column.addWidget(self.number_label)
        column.addWidget(self.title_label)
        column.addWidget(self.subtitle_label)
        column.addStretch(1)

    def set_state(self, state: str) -> None:
        self.setProperty("state", state)
        self.style().unpolish(self)
        self.style().polish(self)


class SignalCanvas(FigureCanvas):

    def __init__(self) -> None:
        self.figure = Figure(figsize=(10, 7), constrained_layout=True)
        super().__init__(self.figure)
        self.axes = self.figure.subplots(2, 2)
        self.figure.patch.set_facecolor(THEME["bg_app"])
        self._apply_theme()

    def _apply_theme(self) -> None:
        for ax in self.axes.flat:
            ax.set_facecolor(THEME["bg_input"])
            ax.tick_params(
                colors=THEME["text_secondary"],
                labelsize=12,
                direction="out",
                length=3,
                width=0.7,
            )
            ax.grid(True, alpha=0.45, color=THEME["divider"], linewidth=0.6)
            for spine in ax.spines.values():
                spine.set_color(THEME["border_subtle"])
                spine.set_linewidth(0.8)
            ax.title.set_fontsize(14)
            ax.title.set_fontweight("medium")
            ax.xaxis.label.set_fontsize(12)
            ax.yaxis.label.set_fontsize(12)
            ax.margins(x=0.01)

    def draw_placeholder(self) -> None:
        titles = ["发送时域波形", "接收时域波形", "接收频谱", "实时BER"]
        for ax, title in zip(self.axes.flat, titles):
            ax.clear()
            ax.set_title(title, color=THEME["text_primary"], fontsize=14, pad=8)
            ax.text(
                0.5,
                0.5,
                "等待实验数据",
                color=THEME["text_secondary"],
                ha="center",
                va="center",
                transform=ax.transAxes,
            )
        self._apply_theme()
        self.draw_idle()

    def update_plots(
        self,
        config: ExperimentConfig,
        tx_wave: np.ndarray,
        rx_wave: np.ndarray,
        ber_history: List[float],
    ) -> None:
        fs = config.sample_rate_mhz * 1e6
        t_us = np.arange(len(tx_wave)) / fs * 1e6

        ax = self.axes[0, 0]
        ax.clear()
        ax.plot(t_us, np.real(tx_wave), color=THEME["chart_tx"], linewidth=0.9)
        ax.set_title("发送时域波形", color=THEME["text_primary"])
        ax.set_xlabel("时间 / μs", color=THEME["text_secondary"])
        ax.set_ylabel("幅度", color=THEME["text_secondary"])

        ax = self.axes[0, 1]
        ax.clear()
        ax.plot(t_us, np.real(rx_wave), color=THEME["chart_rx"], linewidth=0.9)
        ax.set_title("接收时域波形", color=THEME["text_primary"])
        ax.set_xlabel("时间 / μs", color=THEME["text_secondary"])
        ax.set_ylabel("幅度", color=THEME["text_secondary"])

        ax = self.axes[1, 0]
        ax.clear()
        spectrum = np.fft.fftshift(np.fft.fft(rx_wave))
        freq_mhz = np.fft.fftshift(np.fft.fftfreq(len(rx_wave), d=1.0 / fs)) / 1e6
        spectrum_db = 20.0 * np.log10(np.maximum(np.abs(spectrum), 1e-12))
        spectrum_db -= np.max(spectrum_db)
        ax.plot(freq_mhz, spectrum_db, color=THEME["chart_spectrum"], linewidth=0.9)
        ax.set_title("接收频谱", color=THEME["text_primary"])
        ax.set_xlabel("频率 / MHz", color=THEME["text_secondary"])
        ax.set_ylabel("归一化幅度 / dB", color=THEME["text_secondary"])
        ax.set_ylim(-70, 5)

        ax = self.axes[1, 1]
        ax.clear()
        if ber_history:
            ax.plot(
                np.arange(1, len(ber_history) + 1),
                np.asarray(ber_history) * 100.0,
                color=THEME["chart_ber"],
                marker="o",
                markersize=2.5,
                linewidth=1.0,
            )
        ax.set_title("实时BER", color=THEME["text_primary"])
        ax.set_xlabel("已处理帧", color=THEME["text_secondary"])
        ax.set_ylabel("BER / %", color=THEME["text_secondary"])
        ax.set_ylim(bottom=0)

        self._apply_theme()
        self.draw_idle()


class ReceiveWaveCanvas(FigureCanvas):

    def __init__(self) -> None:
        self.figure = Figure(figsize=(9, 3.8), constrained_layout=True)
        self.figure.patch.set_facecolor(THEME["bg_panel"])
        super().__init__(self.figure)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(280, 180)
        self.setAccessibleName("接收时域波形，模拟后端，显示实部")
        self.ax = self.figure.add_subplot(111)
        self.ax.set_facecolor(THEME["bg_input"])
        self.ax.tick_params(colors=THEME["text_secondary"], labelsize=11, length=3)
        self.ax.xaxis.set_major_locator(MaxNLocator(nbins=6, min_n_ticks=3))
        self.ax.yaxis.set_major_locator(MaxNLocator(nbins=5, min_n_ticks=3))
        self.ax.xaxis.set_minor_locator(AutoMinorLocator(4))
        self.ax.yaxis.set_minor_locator(AutoMinorLocator(2))
        self.ax.grid(which="major", color="#29435F", linewidth=0.7)
        self.ax.grid(which="minor", color="#172A40", linewidth=0.4)
        for spine in self.ax.spines.values():
            spine.set_color(THEME["border_subtle"])
        self.ax.set_xlabel("时间 / μs", color=THEME["text_secondary"], fontsize=11)
        self.ax.set_ylabel("相对幅度（实部）", color=THEME["text_secondary"], fontsize=11)
        self.line, = self.ax.plot([], [], color=THEME["chart_rx"], linewidth=1.1)
        self.empty_text = self.ax.text(
            0.5, 0.5, "等待实验数据", transform=self.ax.transAxes,
            color=THEME["text_secondary"], ha="center", va="center", fontsize=12,
        )
        self.draw_placeholder()

    def draw_placeholder(self) -> None:
        self.line.set_data([], [])
        self.ax.set_xlim(0, 1)
        self.ax.set_ylim(-1.2, 1.2)
        self.empty_text.set_visible(True)
        self.draw_idle()

    def update_waveform(self, config: ExperimentConfig, samples: np.ndarray) -> None:
        values = np.real(samples)
        if not values.size:
            self.draw_placeholder()
            return
        sample_period_us = 1.0 / config.sample_rate_mhz
        time_us = np.arange(values.size) * sample_period_us
        self.line.set_data(time_us, values)
        self.empty_text.set_visible(False)
        self.ax.set_xlim(0, max(float(time_us[-1]), sample_period_us))
        low, high = float(np.min(values)), float(np.max(values))
        padding = max((high - low) * 0.12, 0.05)
        self.ax.set_ylim(low - padding, high + padding)
        self.draw_idle()


class MockSimulation:

    def __init__(self) -> None:
        self.reset(20260919)

    def reset(self, seed: int) -> None:
        bit_seed, wave_seed = np.random.SeedSequence(seed).spawn(2)
        self.rng = np.random.default_rng(bit_seed)
        self.wave_rng = np.random.default_rng(wave_seed)

    @staticmethod
    def estimate_ber(config: ExperimentConfig) -> float:
        effective_snr = config.snr_db - config.attenuation_db
        if "Nakagami" in config.channel_mode:
            fading_penalty = 3.5 / max(config.nakagami_m, 0.2)
            effective_snr -= min(fading_penalty, 10.0)
        linear = 10.0 ** (effective_snr / 10.0)
        ber = 0.5 * math.erfc(math.sqrt(max(linear, 1e-9) / 2.0))
        return float(np.clip(ber, 0.000001, 0.45))

    def process_bits(
        self, bits: np.ndarray, config: ExperimentConfig
    ) -> Tuple[np.ndarray, int]:
        probability = self.estimate_ber(config)
        flips = self.rng.random(bits.size) < probability
        received = np.bitwise_xor(bits.astype(np.uint8), flips.astype(np.uint8))
        return received, int(np.count_nonzero(flips))

    def make_waveforms(
        self, config: ExperimentConfig, symbol: int = 1
    ) -> Tuple[np.ndarray, np.ndarray]:
        fs = config.sample_rate_mhz * 1e6
        duration = config.chirp_duration_us * 1e-6
        bandwidth = config.bandwidth_mhz * 1e6
        n = max(64, int(round(fs * duration)))
        n = min(n, 4096)
        t = np.arange(n) / fs
        slope = (bandwidth / duration) * (1 if symbol else -1)
        tx = np.exp(1j * np.pi * slope * t**2)

        signal_power = np.mean(np.abs(tx) ** 2)
        snr_linear = 10.0 ** ((config.snr_db - config.attenuation_db) / 10.0)
        noise_power = signal_power / max(snr_linear, 1e-9)
        noise = np.sqrt(noise_power / 2.0) * (
            self.wave_rng.standard_normal(n) + 1j * self.wave_rng.standard_normal(n)
        )
        rx = tx.copy()
        if "Nakagami" in config.channel_mode:
            m = max(config.nakagami_m, 0.2)
            amp = math.sqrt(self.wave_rng.gamma(shape=m, scale=1.0 / m))
            phase = self.wave_rng.uniform(0.0, 2.0 * np.pi)
            rx *= amp * np.exp(1j * phase)
        rx += noise
        return tx, rx


class MainWindow(QMainWindow):
    log_message = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(1460, 900)
        self.setMinimumSize(1180, 720)

        self.config = ExperimentConfig()
        self.stats = ExperimentStats()
        self.simulator = MockSimulation()
        self.running = False
        self.run_state = "idle"
        self.termination_reason = None
        self._run_started_monotonic = None
        self._waveform_cache = None
        self._locked_control_states = {}
        self._session_id = None
        self.session_directory = None
        self._session_saved = False
        self._session_log_lines = []
        self._payload_source = ""
        self._recorded_session_ids = set()
        self.payload = b""
        self.tx_bits_array = np.array([], dtype=np.uint8)
        self.rx_bits_array = np.array([], dtype=np.uint8)
        self.bit_cursor = 0
        self.ber_history: List[float] = []
        self.experiment_rows: List[Dict[str, object]] = []
        self.frame_events: List[str] = []
        self.custom_presets: Dict[str, Dict[str, object]] = self._load_custom_presets()

        self.timer = QTimer(self)
        self.timer.setInterval(350)
        self.timer.timeout.connect(self._process_next_frame)
        self.log_message.connect(self._append_log)

        self._build_ui()
        self._apply_style()
        self._wire_events()
        self._set_experiment_controls_locked(False)
        self._refresh_all()
        self.log("系统启动：当前为单文件 V0.11 实验可靠性界面，默认使用模拟后端。")

    def _build_ui(self) -> None:
        central = QWidget()
        central.setObjectName("appRoot")
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(UI_METRICS["sidebar_width"])
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(12, 20, 12, 12)
        sidebar_layout.setSpacing(UI_METRICS["space_8"])

        title = QLabel("RF / CHIRP")
        title.setObjectName("brand")
        subtitle = QLabel("射频通信实验平台 V0.11")
        subtitle.setObjectName("brandSub")
        sidebar_layout.addWidget(title)
        sidebar_layout.addWidget(subtitle)
        sidebar_layout.addSpacing(UI_METRICS["space_16"])

        self.nav = QListWidget()
        self.nav.setObjectName("nav")
        self.nav.setAccessibleName("主导航")
        self.nav.setSpacing(4)
        for text in ["系统总览", "收发控制", "实时监视", "性能分析", "实验记录", "系统日志", "术语说明"]:
            self.nav.addItem(QListWidgetItem(text))
        self.nav.setCurrentRow(0)
        sidebar_layout.addWidget(self.nav, 1)

        self.mode_badge = QLabel("● 模拟模式")
        self.mode_badge.setObjectName("modeBadge")
        sidebar_layout.addWidget(self.mode_badge)

        content = QWidget()
        content.setObjectName("contentRoot")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        top_strip = QFrame()
        top_strip.setObjectName("topStrip")
        top_strip.setMinimumHeight(50)
        top_layout = QHBoxLayout(top_strip)
        top_layout.setContentsMargins(16, 8, 16, 8)
        top_layout.setSpacing(UI_METRICS["space_4"])
        self.top_title = QLabel("通信链路总览")
        self.top_title.setObjectName("topTitle")
        self.top_matlab = StatusPill("MATLAB", "待接入")
        self.top_fpga = StatusPill("FPGA", "待接入")
        self.top_attenuator = StatusPill("衰减模块", "未配置")
        self.top_clock_label = QLabel()
        self.top_clock_label.setObjectName("topClock")
        top_layout.addWidget(self.top_title)
        top_layout.addStretch(1)
        top_layout.addWidget(self.top_matlab)
        top_divider_1 = QFrame()
        top_divider_1.setObjectName("toolbarDivider")
        top_layout.addWidget(top_divider_1)
        top_layout.addWidget(self.top_fpga)
        top_divider_2 = QFrame()
        top_divider_2.setObjectName("toolbarDivider")
        top_layout.addWidget(top_divider_2)
        top_layout.addWidget(self.top_attenuator)
        top_layout.addSpacing(UI_METRICS["space_12"])
        top_layout.addWidget(self.top_clock_label)

        self.stack = QStackedWidget()
        self.stack.setObjectName("pageStack")
        self.overview_page = self._build_overview_page()
        self.tx_page = self._build_tx_page()
        self.rx_page = self._build_rx_page()
        self.analysis_page = self._build_analysis_page()
        self.records_page = self._build_records_page()
        self.log_page = self._build_log_page()
        self.glossary_page = self._build_glossary_page()
        for page in [
            self.overview_page,
            self.tx_page,
            self.rx_page,
            self.analysis_page,
            self.records_page,
            self.log_page,
            self.glossary_page,
        ]:
            self.stack.addWidget(page)
        for page_title, page in [
            ("系统总览", self.overview_page),
            ("收发控制", self.tx_page),
            ("实时监视", self.rx_page),
            ("性能分析", self.analysis_page),
            ("实验记录", self.records_page),
            ("系统日志", self.log_page),
        ]:
            self._attach_page_term_tooltips(page, PAGE_TERM_KEYS[page_title])

        content_layout.addWidget(top_strip)
        content_layout.addWidget(self.stack, 1)
        root.addWidget(sidebar)
        root.addWidget(content, 1)
        self.setCentralWidget(central)

        status = QStatusBar()
        self.status_label = QLabel("就绪")
        self.clock_label = QLabel()
        status.addWidget(self.status_label, 1)
        status.addPermanentWidget(QLabel("数据源：模拟后端"))
        status.addPermanentWidget(self.clock_label)
        self.setStatusBar(status)

        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self._update_clock)
        self.clock_timer.start(1000)
        self._update_clock()

    def _page_container(self, page_title: str, description: str) -> Tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        page.setObjectName("pageRoot")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(UI_METRICS["space_16"])
        heading = QHBoxLayout()
        heading.setSpacing(UI_METRICS["space_8"])
        title = QLabel(page_title)
        title.setObjectName("pageTitle")
        heading.addWidget(title)
        term_keys = PAGE_TERM_KEYS.get(page_title, [])
        if term_keys:
            help_button = QToolButton()
            help_button.setObjectName("pageTermHelp")
            help_button.setText("本页术语")
            help_button.setAccessibleName("打开本页专业术语说明")
            help_button.setToolTip("查看本页涉及的专业术语；同一术语在本页仅列出一次。")
            help_button.clicked.connect(
                lambda checked=False, keys=tuple(dict.fromkeys(term_keys)), title_text=page_title:
                    self._show_term_dialog(title_text + " · 术语说明", keys)
            )
            heading.addWidget(help_button)
        heading.addStretch(1)
        desc = QLabel(description)
        desc.setObjectName("pageDesc")
        desc.setWordWrap(True)
        layout.addLayout(heading)
        layout.addWidget(desc)
        return page, layout

    def _build_overview_page(self) -> QWidget:
        page, layout = self._page_container(
            "系统总览",
            "从数据输入到误码统计的完整链路。当前节点会随模拟实验进度高亮。",
        )

        hero = QFrame()
        hero.setObjectName("heroPanel")
        hero.setMinimumHeight(134)
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(20, 16, 20, 16)
        hero_layout.setSpacing(24)
        hero_text = QVBoxLayout()
        hero_text.setSpacing(UI_METRICS["space_4"])
        self.hero_status = QLabel("系统就绪")
        self.hero_status.setObjectName("heroStatus")
        self.hero_detail = QLabel("配置参数后开始模拟实验，观察数据沿链路完成发送、信道、同步和解调。")
        self.hero_detail.setObjectName("heroDetail")
        self.hero_detail.setWordWrap(True)
        hero_text.addWidget(self.hero_status)
        hero_text.addWidget(self.hero_detail)
        hero_layout.addLayout(hero_text, 3)

        self.ov_mode = QLabel("模拟模式")
        self.ov_modulation = QLabel("Binary Chirp")
        self.ov_channel = QLabel("Nakagami多径 + AWGN")
        self.ov_snr = QLabel("15.0 dB")
        snapshot = QFormLayout()
        snapshot.setContentsMargins(0, 0, 0, 0)
        snapshot.setHorizontalSpacing(16)
        snapshot.setVerticalSpacing(8)
        for label in [self.ov_mode, self.ov_modulation, self.ov_channel, self.ov_snr]:
            label.setObjectName("valueText")
        snapshot.addRow("模式", self.ov_mode)
        snapshot.addRow("调制", self.ov_modulation)
        snapshot.addRow("信道", self.ov_channel)
        snapshot.addRow("SNR", self.ov_snr)
        for field in [self.ov_mode, self.ov_modulation, self.ov_channel, self.ov_snr]:
            snapshot.labelForField(field).setObjectName("formLabel")
        hero_layout.addLayout(snapshot, 2)
        layout.addWidget(hero)

        flow_panel = QFrame()
        flow_panel.setObjectName("sectionPanel")
        flow_panel.setMinimumHeight(178)
        flow_panel.setMaximumHeight(196)
        flow_layout = QVBoxLayout(flow_panel)
        flow_layout.setContentsMargins(16, 12, 16, 14)
        flow_layout.setSpacing(UI_METRICS["space_8"])
        flow_header = QHBoxLayout()
        flow_title = QLabel("实时通信链路")
        flow_title.setObjectName("sectionTitle")
        self.flow_state_label = QLabel("等待开始")
        self.flow_state_label.setObjectName("hintLabel")
        flow_header.addWidget(flow_title)
        flow_header.addStretch(1)
        flow_header.addWidget(self.flow_state_label)
        flow_layout.addLayout(flow_header)

        flow_content = QWidget()
        flow_content.setObjectName("flowContent")
        flow_content.setAccessibleName("实时通信链路")
        flow_content.setMinimumHeight(112)
        flow_content.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        nodes_layout = QHBoxLayout(flow_content)
        nodes_layout.setContentsMargins(0, 0, 0, 0)
        nodes_layout.setSpacing(2)
        node_specs = [
            ("01", "数据输入", "文本 / 文件"),
            ("02", "数据成帧", "同步头 + 净荷"),
            ("03", "Chirp调制", "正 / 负斜率"),
            ("04", "信道", "Nakagami + AWGN"),
            ("05", "帧同步", "粗同步 + 细同步"),
            ("06", "解调判决", "Dechirp + FFT"),
            ("07", "结果统计", "内容 + BER"),
        ]
        self.flow_nodes: List[FlowNode] = []
        for index, spec in enumerate(node_specs):
            node = FlowNode(*spec)
            self.flow_nodes.append(node)
            nodes_layout.addWidget(node, 1)
            if index < len(node_specs) - 1:
                connector = QLabel("›")
                connector.setObjectName("flowArrow")
                connector.setAlignment(Qt.AlignCenter)
                connector.setFixedWidth(10)
                nodes_layout.addWidget(connector, 0, Qt.AlignVCenter)
        flow_layout.addWidget(flow_content)
        layout.addWidget(flow_panel)

        metrics = QGridLayout()
        metrics.setContentsMargins(0, 0, 0, 0)
        metrics.setSpacing(UI_METRICS["space_12"])
        self.card_ber = MetricCard("累计BER", "0.0000 %", THEME["danger"], "%")
        self.card_rate = MetricCard("模拟处理速率", "0.00 kbit/s", THEME["success"], "kbit/s")
        self.card_rate.setToolTip("接收比特数除以模拟流程耗时，包含界面与定时器等待；不代表无线链路吞吐率，结束后冻结。")
        self.card_frames = MetricCard("帧进度", "0 / 0", THEME["accent"])
        self.card_bits = MetricCard("收发比特", "0 / 0", "#B598FF")
        metric_items = [self.card_ber, self.card_rate, self.card_frames, self.card_bits]
        for index, metric in enumerate(metric_items):
            metrics.addWidget(metric, 0, index)
            metrics.setColumnStretch(index, [10, 12, 9, 9][index])
        layout.addLayout(metrics)

        control_panel = QFrame()
        control_panel.setObjectName("sectionPanel")
        control_layout = QHBoxLayout(control_panel)
        control_layout.setContentsMargins(16, 12, 16, 12)
        control_layout.setSpacing(8)
        self.quick_start_btn = QPushButton("开始模拟实验")
        self.quick_start_btn.setObjectName("primaryButton")
        self.quick_stop_btn = QPushButton("停止")
        self.quick_stop_btn.setObjectName("dangerButton")
        self.quick_reset_btn = QPushButton("复位统计")
        self.quick_reset_btn.setObjectName("ghostButton")
        self.overview_progress = QProgressBar()
        self.overview_progress.setAccessibleName("总览实验进度")
        self.overview_progress.setRange(0, 100)
        self.overview_progress.setValue(0)
        control_layout.addWidget(self.quick_start_btn)
        control_layout.addWidget(self.quick_stop_btn)
        control_layout.addWidget(self.quick_reset_btn)
        control_layout.addWidget(self.overview_progress, 1)
        layout.addWidget(control_panel)
        layout.addStretch(1)
        return page

    def _build_tx_page(self) -> QWidget:
        page, layout = self._page_container(
            "收发控制",
            "左侧创建发送任务并观察回传摘要，右侧设置常用参数；高级参数默认折叠。",
        )

        body = QHBoxLayout()
        body.setSpacing(16)

        task_panel = QFrame()
        task_panel.setObjectName("sectionPanel")
        task_layout = QVBoxLayout(task_panel)
        task_layout.setContentsMargins(16, 12, 16, 12)
        task_layout.setSpacing(UI_METRICS["space_12"])
        task_title = QLabel("发送任务")
        task_title.setObjectName("sectionTitle")
        task_subtitle = QLabel("选择数据来源并启动一次完整收发流程")
        task_subtitle.setObjectName("hintLabel")
        task_layout.addWidget(task_title)
        task_layout.addWidget(task_subtitle)

        source_row = QHBoxLayout()
        self.source_combo = QComboBox()
        self.source_combo.addItems(["文本输入", "随机字节", "本地文件"])
        self.random_bytes_spin = self._int_spin(1, 1000000, 100)
        source_label = QLabel("数据来源")
        source_label.setObjectName("formLabel")
        source_row.addWidget(source_label)
        source_row.addWidget(self.source_combo, 1)
        bytes_label = QLabel("字节数")
        bytes_label.setObjectName("formLabel")
        source_row.addWidget(bytes_label)
        source_row.addWidget(self.random_bytes_spin)
        task_layout.addLayout(source_row)

        file_row = QHBoxLayout()
        self.file_path_edit = QLineEdit()
        self.file_path_edit.setPlaceholderText("选择本地文件")
        self.browse_btn = QPushButton("浏览…")
        file_row.addWidget(self.file_path_edit, 1)
        file_row.addWidget(self.browse_btn)
        task_layout.addLayout(file_row)

        self.payload_edit = QPlainTextEdit()
        self.payload_edit.setPlaceholderText("输入需要发送的文本，例如：hello world")
        self.payload_edit.setPlainText("hello world")
        task_layout.addWidget(self.payload_edit, 1)

        actions = QHBoxLayout()
        self.tx_start_btn = QPushButton("开始模拟实验")
        self.tx_start_btn.setObjectName("primaryButton")
        self.tx_stop_btn = QPushButton("停止")
        self.tx_stop_btn.setObjectName("dangerButton")
        self.tx_reset_btn = QPushButton("复位")
        self.tx_reset_btn.setObjectName("ghostButton")
        self.loop_check = QCheckBox("循环发送（预留）")
        self.loop_check.setEnabled(False)
        actions.addWidget(self.tx_start_btn)
        actions.addWidget(self.tx_stop_btn)
        actions.addWidget(self.tx_reset_btn)
        actions.addStretch(1)
        actions.addWidget(self.loop_check)
        task_layout.addLayout(actions)

        self.control_progress = QProgressBar()
        self.control_progress.setAccessibleName("收发实验进度")
        self.control_progress.setRange(0, 100)
        task_layout.addWidget(self.control_progress)

        return_panel = QFrame()
        return_panel.setObjectName("returnPanel")
        return_layout = QVBoxLayout(return_panel)
        return_layout.setContentsMargins(12, 8, 12, 8)
        return_header = QHBoxLayout()
        return_header.addWidget(QLabel("接收摘要"))
        return_header.addStretch(1)
        self.control_rx_status = QLabel("等待数据")
        self.control_rx_status.setObjectName("statusGood")
        return_header.addWidget(self.control_rx_status)
        self.control_rx_preview = QLabel("尚未收到内容")
        self.control_rx_preview.setObjectName("rxPreview")
        self.control_rx_preview.setWordWrap(True)
        return_layout.addLayout(return_header)
        return_layout.addWidget(self.control_rx_preview)
        task_layout.addWidget(return_panel)

        settings_scroll = QScrollArea()
        settings_scroll.setObjectName("settingsScroll")
        settings_scroll.setWidgetResizable(True)
        settings_scroll.setFrameShape(QFrame.NoFrame)
        settings_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        settings_widget = QWidget()
        settings_widget.setObjectName("settingsWidget")
        settings_layout = QVBoxLayout(settings_widget)
        settings_layout.setContentsMargins(0, 0, 0, 0)
        settings_layout.setSpacing(UI_METRICS["space_8"])

        common_panel = QFrame()
        common_panel.setObjectName("sectionPanel")
        common_layout = QVBoxLayout(common_panel)
        common_layout.setContentsMargins(16, 12, 16, 12)
        common_header = QHBoxLayout()
        common_title = QLabel("常用参数")
        common_title.setObjectName("sectionTitle")
        self.preset_combo = QComboBox()
        self.preset_combo.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.preset_combo.setMinimumWidth(0)
        self.save_preset_btn = QPushButton("保存预设")
        self.save_preset_btn.setObjectName("ghostButton")
        self.delete_preset_btn = QPushButton("删除预设")
        self.delete_preset_btn.setObjectName("ghostButton")
        common_header.addWidget(common_title)
        common_header.addStretch(1)
        common_header.addWidget(QLabel("场景预设"))
        common_header.addWidget(self.preset_combo, 1)
        common_header.addWidget(self.save_preset_btn)
        common_header.addWidget(self.delete_preset_btn)
        common_layout.addLayout(common_header)
        self._refresh_preset_combo()
        common_form = QFormLayout()
        common_form.setHorizontalSpacing(UI_METRICS["space_12"])
        common_form.setVerticalSpacing(UI_METRICS["space_8"])
        common_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.work_mode_combo = QComboBox()
        self.work_mode_combo.addItems(["模拟模式", "MATLAB模式（待接入）", "FPGA模式（待接入）"])
        self.modulation_combo = QComboBox()
        self.modulation_combo.addItems(
            [
                "Binary Chirp（正/负斜率）",
                "FSK（预留）",
                "BPSK（预留）",
                "QPSK（预留）",
            ]
        )
        for index in range(1, self.modulation_combo.count()):
            self.modulation_combo.model().item(index).setEnabled(False)
        self.coding_combo = QComboBox()
        self.coding_combo.addItems(["当前单一编码", "无编码（预留）", "其他编码（预留）"])
        self.channel_combo = QComboBox()
        self.channel_combo.addItems(["Nakagami多径 + AWGN", "仅AWGN", "真实硬件信道（预留）"])
        self.snr_spin = self._double_spin(-20.0, 60.0, 15.0, 1.0, " dB")
        self.attenuation_spin = self._double_spin(0.0, 120.0, 0.0, 1.0, " dB")
        common_form.addRow("工作模式", self.work_mode_combo)
        common_form.addRow("调制方式", self.modulation_combo)
        common_form.addRow("信源编码", self.coding_combo)
        common_form.addRow("信道模型", self.channel_combo)
        common_form.addRow("信噪比 SNR", self.snr_spin)
        common_form.addRow("衰减值", self.attenuation_spin)
        for field in [
            self.work_mode_combo,
            self.modulation_combo,
            self.coding_combo,
            self.channel_combo,
            self.snr_spin,
            self.attenuation_spin,
        ]:
            common_form.labelForField(field).setObjectName("formLabel")
            field.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
            field.setMinimumWidth(0)
        common_layout.addLayout(common_form)
        settings_layout.addWidget(common_panel)

        self.advanced_toggle = QToolButton()
        self.advanced_toggle.setObjectName("sectionToggle")
        self.advanced_toggle.setText("高级参数   ›")
        self.advanced_toggle.setCheckable(True)
        self.advanced_toggle.setChecked(False)
        self.advanced_toggle.setToolButtonStyle(Qt.ToolButtonTextOnly)
        settings_layout.addWidget(self.advanced_toggle)

        self.advanced_panel = QFrame()
        self.advanced_panel.setObjectName("sectionPanel")
        advanced_layout = QFormLayout(self.advanced_panel)
        advanced_layout.setContentsMargins(16, 12, 16, 12)
        advanced_layout.setHorizontalSpacing(UI_METRICS["space_12"])
        advanced_layout.setVerticalSpacing(UI_METRICS["space_8"])
        advanced_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.fs_spin = self._double_spin(1.0, 200.0, 56.0, 1.0, " MHz")
        self.bandwidth_spin = self._double_spin(0.1, 100.0, 7.0, 0.5, " MHz")
        self.duration_spin = self._double_spin(0.1, 1000.0, 10.0, 1.0, " μs")
        self.frame_spin = self._int_spin(2, 4096, 30)
        self.sync_spin = self._int_spin(1, 1024, 13)
        self.guard_spin = self._double_spin(0.0, 200.0, 20.0, 5.0, " %")
        self.nakagami_spin = self._double_spin(0.2, 20.0, 0.5, 0.1, "")
        self.seed_spin = self._int_spin(0, 2147483647, 20260919)
        self.doppler_edit = QLineEdit("源代码暂无此参数")
        self.doppler_edit.setEnabled(False)
        advanced_layout.addRow("采样率", self.fs_spin)
        advanced_layout.addRow("Chirp带宽", self.bandwidth_spin)
        advanced_layout.addRow("Chirp时长", self.duration_spin)
        advanced_layout.addRow("每帧符号数", self.frame_spin)
        advanced_layout.addRow("同步头长度", self.sync_spin)
        advanced_layout.addRow("保护间隔", self.guard_spin)
        advanced_layout.addRow("Nakagami m", self.nakagami_spin)
        advanced_layout.addRow("随机种子", self.seed_spin)
        advanced_layout.addRow("多普勒", self.doppler_edit)
        for field in [
            self.fs_spin,
            self.bandwidth_spin,
            self.duration_spin,
            self.frame_spin,
            self.sync_spin,
            self.guard_spin,
            self.nakagami_spin,
            self.seed_spin,
            self.doppler_edit,
        ]:
            advanced_layout.labelForField(field).setObjectName("formLabel")
            field.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
            field.setMinimumWidth(0)
        self.advanced_panel.setVisible(False)
        settings_layout.addWidget(self.advanced_panel)
        settings_layout.addStretch(1)
        settings_scroll.setWidget(settings_widget)

        body.addWidget(task_panel, 3)
        body.addWidget(settings_scroll, 2)
        layout.addLayout(body, 1)

        self.random_bytes_spin.setEnabled(False)
        self.file_path_edit.setEnabled(False)
        self.browse_btn.setEnabled(False)
        return page

    def _build_rx_page(self) -> QWidget:
        page, layout = self._page_container(
            "实时监视", "接收时域波形优先；同屏查看接收内容、原始字节与最近帧。"
        )
        layout.setContentsMargins(20, 14, 20, 14)
        layout.setSpacing(10)

        stats_panel = QFrame()
        stats_panel.setObjectName("metricStrip")
        stats_grid = QGridLayout(stats_panel)
        stats_grid.setContentsMargins(12, 10, 12, 10)
        stats_grid.setHorizontalSpacing(12)
        self.rx_metric_labels: Dict[str, QLabel] = {}
        names = [
            ("接收状态", "等待数据"), ("已接收比特", "0"), ("错误比特", "0"),
            ("累计BER", "0.0000 %"), ("正确/错误/丢帧", "0 / 0 / 0"),
        ]
        for index, (name, value) in enumerate(names):
            group = QWidget()
            column = QVBoxLayout(group)
            column.setContentsMargins(6, 0, 6, 0)
            column.setSpacing(4)
            caption = QLabel(name)
            caption.setObjectName("cardTitle")
            label = QLabel(value)
            label.setObjectName("rxMetricValue")
            label.setProperty("accent", name == "累计BER")
            column.addWidget(caption)
            column.addWidget(label)
            self.rx_metric_labels[name] = label
            stats_grid.addWidget(group, 0, index)
            stats_grid.setColumnStretch(index, 1)
        layout.addWidget(stats_panel)

        self.rx_splitter = QSplitter(Qt.Horizontal)
        self.rx_splitter.setObjectName("rxSplitter")
        self.rx_splitter.setChildrenCollapsible(False)
        self.rx_splitter.setHandleWidth(12)
        wave_panel = QFrame()
        wave_panel.setObjectName("sectionPanel")
        wave_layout = QVBoxLayout(wave_panel)
        wave_layout.setContentsMargins(12, 10, 12, 8)
        wave_layout.setSpacing(4)
        title = QLabel("接收时域波形")
        title.setObjectName("sectionTitle")
        wave_layout.addWidget(title)
        self.rx_wave_info = QLabel("模拟后端 · 最近一次绘图刷新 · 显示接收信号实部")
        self.rx_wave_info.setWordWrap(True)
        self.rx_wave_info.setObjectName("hintLabel")
        wave_layout.addWidget(self.rx_wave_info)
        self.rx_canvas = ReceiveWaveCanvas()
        wave_layout.addWidget(self.rx_canvas, 1)

        text_panel = QFrame()
        text_panel.setObjectName("sectionPanel")
        text_panel.setMinimumWidth(240)
        text_layout = QVBoxLayout(text_panel)
        text_layout.setContentsMargins(12, 10, 12, 10)
        text_layout.setSpacing(8)
        text_title = QLabel("接收内容")
        text_title.setObjectName("sectionTitle")
        text_layout.addWidget(text_title)
        self.rx_view_combo = QComboBox()
        self.rx_view_combo.addItems(["文本视图", "十六进制视图"])
        self.rx_view_combo.setAccessibleName("接收内容视图")
        text_layout.addWidget(self.rx_view_combo)
        self.received_text = QPlainTextEdit()
        self.received_text.setAccessibleName("接收文本内容")
        self.received_text.setReadOnly(True)
        self.received_text.setPlaceholderText("接收到的文本将在此显示")
        self.received_hex = QPlainTextEdit()
        self.received_hex.setObjectName("hexView")
        self.received_hex.setAccessibleName("接收十六进制内容")
        self.received_hex.setReadOnly(True)
        self.received_hex.setPlaceholderText("接收字节的十六进制表示")
        self.received_hex.setVisible(False)
        text_layout.addWidget(self.received_text, 1)
        text_layout.addWidget(self.received_hex, 1)
        hex_title = QLabel("当前原始字节")
        hex_title.setObjectName("cardTitle")
        text_layout.addWidget(hex_title)
        self.hex_preview_label = QLabel("--")
        self.hex_preview_label.setObjectName("monoPreview")
        self.hex_preview_label.setWordWrap(True)
        self.hex_preview_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        hex_scroll = QScrollArea()
        hex_scroll.setWidgetResizable(True)
        hex_scroll.setFrameShape(QFrame.NoFrame)
        hex_scroll.setMinimumHeight(48)
        hex_scroll.setMaximumHeight(92)
        hex_scroll.setWidget(self.hex_preview_label)
        text_layout.addWidget(hex_scroll)
        self.rx_splitter.addWidget(wave_panel)
        self.rx_splitter.addWidget(text_panel)
        self.rx_splitter.setStretchFactor(0, 7)
        self.rx_splitter.setStretchFactor(1, 3)
        self.rx_splitter.setSizes([900, 350])
        layout.addWidget(self.rx_splitter, 1)

        frames_panel = QFrame()
        frames_panel.setObjectName("sectionPanel")
        frames_layout = QVBoxLayout(frames_panel)
        frames_layout.setContentsMargins(12, 8, 12, 8)
        frames_layout.setSpacing(4)
        frames_header = QHBoxLayout()
        frames_title = QLabel("最近帧")
        frames_title.setObjectName("sectionTitle")
        self.frame_summary_label = QLabel("正确 0 · 错误 0 · 丢失 0")
        self.frame_summary_label.setObjectName("hintLabel")
        frames_header.addWidget(frames_title)
        frames_header.addStretch(1)
        frames_header.addWidget(self.frame_summary_label)
        frames_layout.addLayout(frames_header)
        self.recent_frames = QListWidget()
        self.recent_frames.setObjectName("recentFrames")
        self.recent_frames.setAccessibleName("最近30帧结果")
        self.recent_frames.setAlternatingRowColors(True)
        self.recent_frames.setMinimumHeight(46)
        self.recent_frames.setMaximumHeight(78)
        frames_layout.addWidget(self.recent_frames)
        layout.addWidget(frames_panel)

        bottom_panel = QFrame()
        bottom_panel.setObjectName("sectionPanel")
        bottom = QHBoxLayout(bottom_panel)
        bottom.setContentsMargins(12, 8, 12, 8)
        self.rx_progress = QProgressBar()
        self.rx_progress.setAccessibleName("接收实验进度")
        self.rx_progress.setRange(0, 100)
        self.rx_pause_btn = QPushButton("暂停刷新（预留）")
        self.rx_pause_btn.setEnabled(False)
        self.rx_pause_btn.setToolTip("真实数据流刷新控制尚未接入")
        self.rx_clear_btn = QPushButton("清空显示")
        self.rx_clear_btn.setToolTip("清空接收文本与字节显示，保留实验统计")
        bottom.addWidget(QLabel("实验进度"))
        bottom.addWidget(self.rx_progress, 1)
        bottom.addWidget(self.rx_pause_btn)
        bottom.addWidget(self.rx_clear_btn)
        layout.addWidget(bottom_panel)
        return page

    def _build_analysis_page(self) -> QWidget:
        page, layout = self._page_container(
            "性能分析",
            "聚焦时域、频域与BER变化。当前曲线来自模拟后端，后续替换为MATLAB或FPGA实测结果。",
        )
        toolbar_panel = QFrame()
        toolbar_panel.setObjectName("toolBarPanel")
        toolbar = QHBoxLayout(toolbar_panel)
        toolbar.setContentsMargins(0, 0, 0, 8)
        toolbar.setSpacing(UI_METRICS["space_8"])
        self.refresh_plot_btn = QPushButton("刷新图形")
        self.export_image_btn = QPushButton("保存图形PNG")
        self.analysis_hint = QLabel("当前数据源：模拟后端")
        self.analysis_hint.setObjectName("hintLabel")
        toolbar.addWidget(self.refresh_plot_btn)
        toolbar.addWidget(self.export_image_btn)
        toolbar.addStretch(1)
        toolbar.addWidget(self.analysis_hint)
        layout.addWidget(toolbar_panel)

        self.canvas = SignalCanvas()
        self.canvas.setObjectName("signalCanvas")
        self.canvas.setAccessibleName("信号性能图表")
        self.canvas.draw_placeholder()
        layout.addWidget(self.canvas, 1)
        return page

    def _build_records_page(self) -> QWidget:
        page, layout = self._page_container(
            "实验记录",
            "集中保存每次实验的参数与结果，后续用于报告、文章和多组性能对比。",
        )
        toolbar = QHBoxLayout()
        self.export_csv_btn = QPushButton("导出实验CSV")
        self.retry_save_btn = QPushButton("重试自动保存")
        self.retry_save_btn.setEnabled(False)
        self.retry_save_btn.setToolTip("保存失败时，保留当前实验结果并重试写入实验目录")
        self.record_summary = QLabel("尚无实验记录")
        self.record_summary.setObjectName("hintLabel")
        toolbar.addWidget(self.export_csv_btn)
        toolbar.addWidget(self.retry_save_btn)
        toolbar.addStretch(1)
        toolbar.addWidget(self.record_summary)
        layout.addLayout(toolbar)

        self.result_table = QTableWidget(0, 9)
        self.result_table.setAccessibleName("实验结果记录")
        self.result_table.setHorizontalHeaderLabels(
            ["时间", "状态", "模式", "信道", "SNR(dB)", "TX(bit)", "错误(bit)", "BER(%)", "帧数"]
        )
        self.result_table.horizontalHeader().setStretchLastSection(True)
        self.result_table.horizontalHeader().setHighlightSections(False)
        for column, width in enumerate([180, 112, 100, 220, 90, 90, 90, 100]):
            self.result_table.setColumnWidth(column, width)
        self.result_table.verticalHeader().setVisible(False)
        self.result_table.verticalHeader().setDefaultSectionSize(36)
        self.result_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.result_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.result_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.result_table.setShowGrid(False)
        self.result_table.setAlternatingRowColors(True)
        layout.addWidget(self.result_table, 1)
        return page

    def _build_log_page(self) -> QWidget:
        page, layout = self._page_container(
            "系统日志",
            "记录参数修改、收发流程、接口状态和异常，便于后续MATLAB与FPGA联调。",
        )
        actions = QHBoxLayout()
        self.log_clear_btn = QPushButton("清空日志")
        self.log_export_btn = QPushButton("导出TXT")
        actions.addWidget(self.log_clear_btn)
        actions.addWidget(self.log_export_btn)
        actions.addStretch(1)
        layout.addLayout(actions)
        self.log_edit = QPlainTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setObjectName("logEdit")
        layout.addWidget(self.log_edit, 1)
        return page

    def _build_glossary_page(self) -> QWidget:
        page, layout = self._page_container(
            "术语说明", "集中查询上位机中的通信、信号处理、统计指标和硬件接口术语。"
        )
        search_row = QHBoxLayout()
        search_label = QLabel("搜索")
        search_label.setObjectName("formLabel")
        self.glossary_search = QLineEdit()
        self.glossary_search.setAccessibleName("搜索专业术语")
        self.glossary_search.setPlaceholderText("输入术语、缩写或解释内容")
        search_row.addWidget(search_label)
        search_row.addWidget(self.glossary_search, 1)
        layout.addLayout(search_row)

        self.glossary_table = QTableWidget(0, 3)
        self.glossary_table.setAccessibleName("专业术语及解释")
        self.glossary_table.setHorizontalHeaderLabels(["术语", "通俗解释", "类别"])
        self.glossary_table.horizontalHeader().setStretchLastSection(True)
        self.glossary_table.horizontalHeader().setHighlightSections(False)
        self.glossary_table.verticalHeader().setVisible(False)
        self.glossary_table.verticalHeader().setDefaultSectionSize(58)
        self.glossary_table.setColumnWidth(0, 220)
        self.glossary_table.setColumnWidth(1, 730)
        self.glossary_table.setWordWrap(True)
        self.glossary_table.setAlternatingRowColors(True)
        self.glossary_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.glossary_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.glossary_table.setSelectionMode(QAbstractItemView.SingleSelection)
        for term, (definition, category) in TERM_GLOSSARY.items():
            row = self.glossary_table.rowCount()
            self.glossary_table.insertRow(row)
            self.glossary_table.setItem(row, 0, QTableWidgetItem(term))
            self.glossary_table.setItem(row, 1, QTableWidgetItem(definition))
            self.glossary_table.setItem(row, 2, QTableWidgetItem(category))
        self.glossary_table.resizeRowsToContents()
        layout.addWidget(self.glossary_table, 1)

        note = QLabel(
            "说明：当前版本使用软件模拟后端。仿真结果用于界面流程演示，不等同于HackRF或其他硬件实测。"
        )
        note.setObjectName("hintLabel")
        note.setWordWrap(True)
        layout.addWidget(note)
        return page

    def _show_term_dialog(self, title: str, term_keys: Tuple[str, ...]) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.resize(820, 520)
        dialog_layout = QVBoxLayout(dialog)
        table = QTableWidget(0, 2)
        table.setHorizontalHeaderLabels(["术语", "解释"])
        table.horizontalHeader().setStretchLastSection(True)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(58)
        table.setColumnWidth(0, 230)
        table.setWordWrap(True)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        for term in dict.fromkeys(term_keys):
            if term not in TERM_GLOSSARY:
                continue
            definition, _category = TERM_GLOSSARY[term]
            row = table.rowCount()
            table.insertRow(row)
            table.setItem(row, 0, QTableWidgetItem(term))
            table.setItem(row, 1, QTableWidgetItem(definition))
        table.resizeRowsToContents()
        dialog_layout.addWidget(table)
        close_button = QPushButton("关闭")
        close_button.clicked.connect(dialog.accept)
        dialog_layout.addWidget(close_button, 0, Qt.AlignRight)
        dialog.exec_()

    def _attach_page_term_tooltips(self, page: QWidget, term_keys: List[str]) -> None:
        widgets = page.findChildren(QWidget)
        for term in dict.fromkeys(term_keys):
            if term not in TERM_GLOSSARY:
                continue
            aliases = [term]
            if "（" in term and "）" in term:
                aliases.extend([term.split("（", 1)[0], term.split("（", 1)[1].split("）", 1)[0]])
            if term == "Nakagami衰落":
                aliases.append("Nakagami")
            if term == "正交解调（Dechirp）":
                aliases.extend(["Dechirp", "解调"])
            for widget in widgets:
                searchable = []
                if isinstance(widget, QLabel):
                    searchable.append(widget.text())
                elif isinstance(widget, (QPushButton, QToolButton)):
                    searchable.append(widget.text())
                elif isinstance(widget, QGroupBox):
                    searchable.append(widget.title())
                elif isinstance(widget, QComboBox):
                    searchable.extend(widget.itemText(i) for i in range(widget.count()))
                elif isinstance(widget, QTableWidget):
                    searchable.extend(
                        widget.horizontalHeaderItem(i).text()
                        for i in range(widget.columnCount())
                        if widget.horizontalHeaderItem(i) is not None
                    )
                haystack = " ".join(searchable).casefold()
                if any(alias.casefold() in haystack for alias in aliases):
                    definition, _category = TERM_GLOSSARY[term]
                    existing = widget.toolTip().strip()
                    tooltip = "{}：{}".format(term, definition)
                    if tooltip not in existing:
                        widget.setToolTip("{}\n{}".format(existing, tooltip).strip())
                    break

    def _filter_glossary(self, text: str) -> None:
        query = text.strip().casefold()
        for row in range(self.glossary_table.rowCount()):
            contents = " ".join(
                self.glossary_table.item(row, col).text()
                for col in range(self.glossary_table.columnCount())
                if self.glossary_table.item(row, col) is not None
            ).casefold()
            self.glossary_table.setRowHidden(row, bool(query) and query not in contents)

    @staticmethod
    def _double_spin(
        minimum: float, maximum: float, value: float, step: float, suffix: str
    ) -> QDoubleSpinBox:
        widget = QDoubleSpinBox()
        widget.setRange(minimum, maximum)
        widget.setValue(value)
        widget.setSingleStep(step)
        widget.setDecimals(3)
        widget.setSuffix(suffix)
        return widget

    @staticmethod
    def _int_spin(minimum: int, maximum: int, value: int) -> QSpinBox:
        widget = QSpinBox()
        widget.setRange(minimum, maximum)
        widget.setValue(value)
        return widget

    def _wire_events(self) -> None:
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.nav.currentRowChanged.connect(self._update_top_title)
        self.quick_start_btn.clicked.connect(self.start_experiment)
        self.tx_start_btn.clicked.connect(self.start_experiment)
        self.quick_stop_btn.clicked.connect(self.stop_experiment)
        self.tx_stop_btn.clicked.connect(self.stop_experiment)
        self.quick_reset_btn.clicked.connect(self.reset_experiment)
        self.tx_reset_btn.clicked.connect(self.reset_experiment)
        self.browse_btn.clicked.connect(self._browse_file)
        self.rx_clear_btn.clicked.connect(self._clear_received_display)
        self.refresh_plot_btn.clicked.connect(self._refresh_plot)
        self.export_csv_btn.clicked.connect(self._export_csv)
        self.retry_save_btn.clicked.connect(self._save_session)
        self.export_image_btn.clicked.connect(self._export_image)
        self.log_clear_btn.clicked.connect(self.log_edit.clear)
        self.log_export_btn.clicked.connect(self._export_log)
        self.work_mode_combo.currentTextChanged.connect(self._mode_changed)
        self.channel_combo.currentTextChanged.connect(self._channel_changed)
        self.source_combo.currentTextChanged.connect(self._source_changed)
        self.advanced_toggle.toggled.connect(self._toggle_advanced)
        self.rx_view_combo.currentIndexChanged.connect(self._toggle_rx_view)
        self.preset_combo.currentTextChanged.connect(self._apply_preset)
        self.save_preset_btn.clicked.connect(self._save_current_preset)
        self.delete_preset_btn.clicked.connect(self._delete_current_preset)
        self.glossary_search.textChanged.connect(self._filter_glossary)

    def _load_custom_presets(self) -> Dict[str, Dict[str, object]]:
        if not PRESET_FILE.exists():
            return {}
        try:
            with PRESET_FILE.open("r", encoding="utf-8") as fp:
                data = json.load(fp)
        except (OSError, json.JSONDecodeError):
            return {}
        presets = data.get("presets", {}) if isinstance(data, dict) else {}
        if not isinstance(presets, dict):
            return {}
        clean_presets: Dict[str, Dict[str, object]] = {}
        for name, values in presets.items():
            if isinstance(name, str) and name.strip() and isinstance(values, dict):
                clean_presets[name.strip()] = dict(values)
        return clean_presets

    def _write_custom_presets(self) -> None:
        payload = {
            "version": 1,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "presets": self.custom_presets,
        }
        with PRESET_FILE.open("w", encoding="utf-8") as fp:
            json.dump(payload, fp, ensure_ascii=False, indent=2)

    def _refresh_preset_combo(self, selected: str = "自定义") -> None:
        self.preset_combo.blockSignals(True)
        self.preset_combo.clear()
        self.preset_combo.addItem("自定义", "custom-placeholder")
        for name in BUILT_IN_PRESETS:
            self.preset_combo.addItem(name, "built-in")
        for name in sorted(self.custom_presets):
            self.preset_combo.addItem(name, "custom")
        index = self.preset_combo.findText(selected)
        self.preset_combo.setCurrentIndex(index if index >= 0 else 0)
        self.preset_combo.blockSignals(False)
        self._update_preset_actions()

    def _update_preset_actions(self) -> None:
        current_type = self.preset_combo.currentData()
        self.delete_preset_btn.setEnabled(current_type == "custom")

    def _config_to_preset(self, config: ExperimentConfig) -> Dict[str, object]:
        return {
            "work_mode": config.work_mode,
            "modulation": config.modulation,
            "source_coding": config.source_coding,
            "channel_mode": config.channel_mode,
            "snr_db": config.snr_db,
            "sample_rate_mhz": config.sample_rate_mhz,
            "bandwidth_mhz": config.bandwidth_mhz,
            "chirp_duration_us": config.chirp_duration_us,
            "frame_length": config.frame_length,
            "sync_length": config.sync_length,
            "guard_percent": config.guard_percent,
            "nakagami_m": config.nakagami_m,
            "attenuation_db": config.attenuation_db,
            "random_seed": config.random_seed,
        }

    def _apply_config_values(self, values: Dict[str, object]) -> None:
        combo_fields = [
            ("work_mode", self.work_mode_combo),
            ("modulation", self.modulation_combo),
            ("source_coding", self.coding_combo),
            ("channel_mode", self.channel_combo),
        ]
        for key, combo in combo_fields:
            value = values.get(key)
            if isinstance(value, str) and combo.findText(value) >= 0:
                combo.setCurrentText(value)

        spin_fields = [
            ("snr_db", self.snr_spin),
            ("sample_rate_mhz", self.fs_spin),
            ("bandwidth_mhz", self.bandwidth_spin),
            ("chirp_duration_us", self.duration_spin),
            ("frame_length", self.frame_spin),
            ("sync_length", self.sync_spin),
            ("guard_percent", self.guard_spin),
            ("nakagami_m", self.nakagami_spin),
            ("attenuation_db", self.attenuation_spin),
            ("random_seed", self.seed_spin),
        ]
        for key, spin in spin_fields:
            value = values.get(key)
            if isinstance(value, (int, float)):
                spin.setValue(value)

    def _save_current_preset(self) -> None:
        name, accepted = QInputDialog.getText(self, "保存参数预设", "预设名称")
        if not accepted:
            return
        name = name.strip()
        if not name:
            QMessageBox.warning(self, "保存预设", "预设名称不能为空。")
            return
        if name == "自定义" or name in BUILT_IN_PRESETS:
            QMessageBox.warning(self, "保存预设", "该名称为内置预设，请换一个名称。")
            return
        if name in self.custom_presets:
            reply = QMessageBox.question(
                self,
                "覆盖预设",
                "自定义预设“{}”已存在，是否覆盖？".format(name),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return
        self.custom_presets[name] = self._config_to_preset(self._collect_config())
        try:
            self._write_custom_presets()
        except OSError as exc:
            QMessageBox.critical(self, "保存预设失败", "无法写入预设文件：{}".format(exc))
            return
        self._refresh_preset_combo(name)
        self.log("已保存自定义参数预设：{}。".format(name))

    def _delete_current_preset(self) -> None:
        name = self.preset_combo.currentText()
        if self.preset_combo.currentData() != "custom" or name not in self.custom_presets:
            QMessageBox.information(self, "删除预设", "只能删除自定义预设，内置预设不会被删除。")
            return
        reply = QMessageBox.question(
            self,
            "删除预设",
            "确定删除自定义预设“{}”吗？".format(name),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        del self.custom_presets[name]
        try:
            self._write_custom_presets()
        except OSError as exc:
            QMessageBox.critical(self, "删除预设失败", "无法更新预设文件：{}".format(exc))
            return
        self._refresh_preset_combo()
        self.log("已删除自定义参数预设：{}。".format(name))

    def _collect_config(self) -> ExperimentConfig:
        return ExperimentConfig(
            work_mode=self.work_mode_combo.currentText(),
            modulation=self.modulation_combo.currentText(),
            source_coding=self.coding_combo.currentText(),
            channel_mode=self.channel_combo.currentText(),
            snr_db=self.snr_spin.value(),
            sample_rate_mhz=self.fs_spin.value(),
            bandwidth_mhz=self.bandwidth_spin.value(),
            chirp_duration_us=self.duration_spin.value(),
            frame_length=self.frame_spin.value(),
            sync_length=self.sync_spin.value(),
            guard_percent=self.guard_spin.value(),
            nakagami_m=self.nakagami_spin.value(),
            attenuation_db=self.attenuation_spin.value(),
            random_seed=self.seed_spin.value(),
        )

    def _validate_config(self, config: ExperimentConfig) -> Optional[str]:
        if config.sync_length >= config.frame_length:
            return "同步头长度必须小于每帧符号数。"
        if config.bandwidth_mhz >= config.sample_rate_mhz:
            return "Chirp带宽应小于采样率。"
        if config.work_mode != "模拟模式":
            return "当前V0.11只实现模拟模式，MATLAB和FPGA接口为结构预留。"
        return None

    def _prepare_payload(self) -> bytes:
        source = self.source_combo.currentText()
        if source == "文本输入":
            return self.payload_edit.toPlainText().encode("utf-8")
        if source == "随机字节":
            rng = np.random.default_rng(self.seed_spin.value())
            return rng.integers(
                0, 256, size=self.random_bytes_spin.value(), dtype=np.uint8
            ).tobytes()
        path_text = self.file_path_edit.text().strip()
        if not path_text:
            raise ValueError("请选择需要发送的本地文件。")
        return Path(path_text).read_bytes()

    def start_experiment(self) -> None:
        if self.running:
            self.log("实验已经在运行。", "WARNING")
            return
        if self._session_id and not self._session_saved and not self._save_session():
            return
        config = self._collect_config()
        error = self._validate_config(config)
        if error:
            QMessageBox.information(self, "接口尚未接入", error)
            self.log(error, "WARNING")
            return
        try:
            payload = self._prepare_payload()
        except Exception as exc:
            QMessageBox.warning(self, "发送内容错误", str(exc))
            self.log("发送内容读取失败：{}".format(exc), "ERROR")
            return
        if not payload:
            QMessageBox.warning(self, "发送内容为空", "请先输入文本、生成随机字节或选择文件。")
            return

        self.config = config
        self._session_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f") + "_" + uuid4().hex[:8]
        self.session_directory = None
        self._session_saved = False
        self._session_log_lines = []
        self._payload_source = self.source_combo.currentText()
        self.termination_reason = None
        self._waveform_cache = None
        self.rx_canvas.draw_placeholder()
        self.canvas.draw_placeholder()
        self.rx_wave_info.setText("模拟后端 · 等待本次实验波形 · 显示接收信号实部")
        self.payload = payload
        self.simulator.reset(config.random_seed)
        self.tx_bits_array = np.unpackbits(np.frombuffer(payload, dtype=np.uint8))
        self.rx_bits_array = np.zeros_like(self.tx_bits_array)
        data_length = config.frame_length - config.sync_length
        total_frames = int(math.ceil(len(self.tx_bits_array) / data_length))
        self.stats = ExperimentStats(
            total_frames=total_frames,
            start_time=datetime.now(),
        )
        self.bit_cursor = 0
        self.ber_history = []
        self.frame_events = []
        self.received_text.clear()
        self.received_hex.clear()
        self.recent_frames.clear()
        self.control_rx_preview.setText("等待第一帧数据…")
        self.running = True
        self.run_state = "running"
        self._run_started_monotonic = monotonic()
        self._set_experiment_controls_locked(True)
        self.timer.start()
        self.status_label.setText("实验运行中")
        self.log(
            "开始实验：{}字节，{}帧，SNR={:.1f} dB，信道={}。".format(
                len(payload), total_frames, config.snr_db, config.channel_mode
            ),
            "TX",
        )
        self._refresh_all()

    def _process_next_frame(self) -> None:
        if not self.running:
            return
        data_length = self.config.frame_length - self.config.sync_length
        start = self.bit_cursor
        end = min(start + data_length, len(self.tx_bits_array))
        tx_chunk = self.tx_bits_array[start:end]
        if tx_chunk.size == 0:
            self._finish_experiment()
            return

        rx_chunk, errors = self.simulator.process_bits(tx_chunk, self.config)
        self.rx_bits_array[start:end] = rx_chunk
        self.bit_cursor = end
        self.stats.processed_frames += 1
        self.stats.tx_bits += int(tx_chunk.size)
        self.stats.rx_bits += int(rx_chunk.size)
        self.stats.error_bits += errors
        if errors:
            self.stats.error_frames += 1
            frame_text = "帧 {:03d}   ✕   {} bit错误".format(
                self.stats.processed_frames, errors
            )
        else:
            self.stats.correct_frames += 1
            frame_text = "帧 {:03d}   ✓   正确".format(self.stats.processed_frames)
        self.frame_events.append(frame_text)
        self.recent_frames.insertItem(0, frame_text)
        if self.recent_frames.count() > 30:
            self.recent_frames.takeItem(self.recent_frames.count() - 1)
        self.ber_history.append(self.stats.ber)

        self._update_received_display()
        self._refresh_all()
        if self.stats.processed_frames == 1 or self.stats.processed_frames % 5 == 0:
            self._capture_waveform()
            self._refresh_plot()

        if self.bit_cursor >= len(self.tx_bits_array):
            self._finish_experiment()

    def _finish_experiment(self) -> None:
        self._finalize_experiment("completed", "completed")

    def stop_experiment(self) -> None:
        self._finalize_experiment("stopped", "stop")

    def reset_experiment(self) -> None:
        if self.running:
            self._finalize_experiment("stopped", "reset")
        if self._session_id and not self._session_saved and not self._save_session():
            return
        self._session_id = None
        self._session_saved = False
        self.session_directory = None
        self._session_log_lines = []
        self._waveform_cache = None
        self.run_state = "idle"
        self._run_started_monotonic = None
        self._set_experiment_controls_locked(False)
        self.timer.stop()
        self.running = False
        self.stats = ExperimentStats()
        self.payload = b""
        self.tx_bits_array = np.array([], dtype=np.uint8)
        self.rx_bits_array = np.array([], dtype=np.uint8)
        self.bit_cursor = 0
        self.ber_history = []
        self.frame_events = []
        self.received_text.clear()
        self.received_hex.clear()
        self.recent_frames.clear()
        self.control_rx_preview.setText("尚未收到内容")
        self.canvas.draw_placeholder()
        self.rx_canvas.draw_placeholder()
        self.rx_wave_info.setText("模拟后端 · 等待实验数据 · 显示接收信号实部")
        self.status_label.setText("就绪")
        self.log("统计已复位。")
        self._refresh_all()

    def _state_text(self) -> str:
        return {"idle": "就绪", "running": "实验运行中", "completed": "实验完成",
                "stopped": "实验已停止"}[self.run_state]

    def _set_experiment_controls_locked(self, locked: bool) -> None:
        controls = [
            self.work_mode_combo, self.modulation_combo, self.coding_combo,
            self.channel_combo, self.snr_spin, self.attenuation_spin,
            self.fs_spin, self.bandwidth_spin, self.duration_spin,
            self.frame_spin, self.sync_spin, self.guard_spin,
            self.nakagami_spin, self.seed_spin, self.source_combo,
            self.random_bytes_spin, self.file_path_edit, self.browse_btn,
            self.payload_edit, self.preset_combo, self.save_preset_btn,
            self.delete_preset_btn,
        ]
        if locked:
            self._locked_control_states = {control: control.isEnabled() for control in controls}
            for control in controls:
                control.setEnabled(False)
        else:
            for control, enabled in self._locked_control_states.items():
                control.setEnabled(enabled)
            self._locked_control_states.clear()
        for button in [self.quick_start_btn, self.tx_start_btn]:
            button.setEnabled(not locked)
        for button in [self.quick_stop_btn, self.tx_stop_btn]:
            button.setEnabled(locked)

    def _capture_waveform(self) -> None:
        symbol = 1
        if self.bit_cursor and self.tx_bits_array.size:
            symbol = int(self.tx_bits_array[self.bit_cursor - 1])
        tx, rx = self.simulator.make_waveforms(self.config, symbol)
        self._waveform_cache = (self.config, tx, rx)

    def _finalize_experiment(self, state: str, reason: str) -> None:
        if not self.running:
            return
        self.timer.stop()
        self.running = False
        self.run_state = state
        self.termination_reason = reason
        self.stats.end_time = datetime.now()
        self.stats.elapsed_seconds = max(monotonic() - self._run_started_monotonic, 1e-6)
        self.stats.unprocessed_frames = max(0, self.stats.total_frames - self.stats.processed_frames)
        self._set_experiment_controls_locked(False)
        if self.bit_cursor:
            self._capture_waveform()
        self.status_label.setText(self._state_text())
        self._refresh_all()
        self._refresh_plot()
        self._record_result()
        self.log("{}：TX={} bit，错误={} bit，BER={:.6f}%，未处理 {} 帧。".format(
            self._state_text(), self.stats.tx_bits, self.stats.error_bits,
            self.stats.ber * 100.0, self.stats.unprocessed_frames,
        ), "RX" if state == "completed" else "WARNING")
        self._save_session()

    def _save_session(self) -> bool:
        if self._session_saved or not self._session_id:
            return True
        if self.running:
            return False
        destination = SESSION_ROOT / self._session_id
        staging = SESSION_ROOT / (self._session_id + ".pending")
        complete_bytes = self.bit_cursor // 8 * 8
        received = np.packbits(self.rx_bits_array[:complete_bytes]).tobytes()
        stats = asdict(self.stats)
        for key in ["start_time", "end_time"]:
            stats[key] = stats[key].isoformat() if stats[key] else None
        result = {
            "schema_version": 1, "app_version": APP_VERSION,
            "session_id": self._session_id, "status": self.run_state,
            "termination_reason": self.termination_reason,
            "backend": "mock", "payload_source": self._payload_source,
            "config": asdict(self.config), "stats": stats,
            "ber": self.stats.ber, "ber_percent": self.stats.ber * 100.0,
            "rx_valid_bits": self.bit_cursor,
            "received_binary_note": "received.bin仅含完整字节；尾部不足8位见received_bits.npy",
            "waveform_note": "独立模拟Chirp片段，不是接收比特的解调来源或硬件实测",
        }
        try:
            SESSION_ROOT.mkdir(parents=True, exist_ok=True)
            staging.mkdir(exist_ok=True)
            (staging / "payload.bin").write_bytes(self.payload)
            (staging / "received.bin").write_bytes(received)
            np.save(str(staging / "received_bits.npy"), self.rx_bits_array[:self.bit_cursor])
            if self._waveform_cache is not None:
                config, tx, rx = self._waveform_cache
                np.savez_compressed(str(staging / "waveforms.npz"), tx=tx, rx=rx,
                                    sample_rate_mhz=config.sample_rate_mhz)
            (staging / "log.txt").write_text("\n".join(self._session_log_lines), encoding="utf-8")
            (staging / "result.json").write_text(
                json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            staging.rename(destination)
        except (OSError, ValueError) as exc:
            self.retry_save_btn.setEnabled(True)
            self.status_label.setText(self._state_text() + " · 自动保存失败，请到实验记录页重试")
            self.log("自动保存失败：{}；当前结果已保留，请检查目录 {} 后重试。".format(
                exc, SESSION_ROOT), "ERROR")
            return False
        self._session_saved = True
        self.session_directory = destination
        self.retry_save_btn.setEnabled(False)
        self.status_label.setText(self._state_text() + " · 已自动保存")
        self.log("实验已自动保存：{}".format(destination))
        return True

    def closeEvent(self, event) -> None:
        if self.running:
            self._finalize_experiment("stopped", "close")
        if self._session_id and not self._session_saved and not self._save_session():
            choice = QMessageBox.question(
                self, "实验尚未保存", "自动保存失败，仍然退出并丢弃未保存结果吗？",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if choice != QMessageBox.Yes:
                event.ignore()
                return
        self.timer.stop()
        self.clock_timer.stop()
        event.accept()

    def _refresh_all(self) -> None:
        config = self.config if self.run_state != "idle" else self._collect_config()
        self.ov_mode.setText(config.work_mode)
        self.ov_modulation.setText(config.modulation)
        self.ov_channel.setText(config.channel_mode)
        self.ov_snr.setText("{:.1f} dB".format(config.snr_db))
        self.card_ber.set_value("{:.4f} %".format(self.stats.ber * 100.0))
        self.card_frames.set_value(
            "{} / {}".format(self.stats.processed_frames, self.stats.total_frames)
        )
        self.card_bits.set_value(
            "{} / {}".format(self.stats.tx_bits, self.stats.rx_bits)
        )

        elapsed = self.stats.elapsed_seconds
        if self.running and self._run_started_monotonic is not None:
            elapsed = max(monotonic() - self._run_started_monotonic, 1e-6)
        rate_kbps = self.stats.rx_bits / elapsed / 1000.0 if elapsed else 0.0
        self.card_rate.set_value("{:.2f} kbit/s".format(rate_kbps))

        progress = 0
        if self.stats.total_frames:
            progress = int(self.stats.processed_frames / self.stats.total_frames * 100)
        self.overview_progress.setValue(progress)
        self.control_progress.setValue(progress)
        self.rx_progress.setValue(progress)

        status_text = {
            "idle": "等待数据", "running": "运行中",
            "completed": "实验完成", "stopped": "实验已停止",
        }[self.run_state]
        self.rx_metric_labels["接收状态"].setText(status_text)
        self.rx_metric_labels["已接收比特"].setText(str(self.stats.rx_bits))
        self.rx_metric_labels["错误比特"].setText(str(self.stats.error_bits))
        self.rx_metric_labels["累计BER"].setText(
            "{:.4f} %".format(self.stats.ber * 100.0)
        )
        self.rx_metric_labels["正确/错误/丢帧"].setText(
            "{} / {} / {}".format(
                self.stats.correct_frames, self.stats.error_frames, self.stats.lost_frames
            )
        )
        self.frame_summary_label.setText(
            "正确 {} · 错误 {} · 丢失 {} · 未处理 {}".format(
                self.stats.correct_frames, self.stats.error_frames,
                self.stats.lost_frames, self.stats.unprocessed_frames,
            )
        )
        self.control_rx_status.setText(status_text)
        if hasattr(self, "record_summary"):
            self.record_summary.setText("共 {} 条实验记录".format(len(self.experiment_rows)))

        self.top_matlab.set_status("接口预留", "idle")
        self.top_fpga.set_status("接口预留", "idle")
        if config.attenuation_db > 0:
            self.top_attenuator.set_status(
                "模拟 {:.1f} dB".format(config.attenuation_db), "working"
            )
        else:
            self.top_attenuator.set_status("未配置", "idle")

        if not self.stats.total_frames:
            self.hero_status.setText("系统就绪")
            self.hero_detail.setText("配置参数后开始模拟实验，观察数据沿链路完成发送、信道、同步和解调。")
            self.flow_state_label.setText("等待开始")
            for node in self.flow_nodes:
                node.set_state("idle")
        elif self.running:
            self.hero_status.setText("通信实验运行中")
            self.hero_detail.setText(
                "正在处理第 {} / {} 帧，当前累计BER为 {:.4f}%。".format(
                    self.stats.processed_frames,
                    self.stats.total_frames,
                    self.stats.ber * 100.0,
                )
            )
            active_index = min(
                len(self.flow_nodes) - 1,
                int(progress / 100.0 * len(self.flow_nodes)),
            )
            self.flow_state_label.setText("数据处理中 · {}%".format(progress))
            for index, node in enumerate(self.flow_nodes):
                node.set_state("done" if index < active_index else "active" if index == active_index else "idle")
        elif self.run_state == "completed":
            self.hero_status.setText("实验完成")
            self.hero_detail.setText(
                "已完成 {} 帧，错误 {} bit，最终BER为 {:.4f}%。".format(
                    self.stats.total_frames,
                    self.stats.error_bits,
                    self.stats.ber * 100.0,
                )
            )
            self.flow_state_label.setText("链路处理完成")
            for index, node in enumerate(self.flow_nodes):
                node.set_state(
                    "warning"
                    if index == len(self.flow_nodes) - 1 and self.stats.error_bits
                    else "done"
                )
        else:
            self.hero_status.setText("实验已停止")
            self.hero_detail.setText("已完成 {}%，剩余帧计入未处理。".format(progress))
            self.flow_state_label.setText("实验已停止 · 未处理 {} 帧".format(self.stats.unprocessed_frames))
            for node in self.flow_nodes:
                node.set_state("idle")

    def _update_received_display(self) -> None:
        complete_bit_count = (self.bit_cursor // 8) * 8
        if complete_bit_count <= 0:
            return
        byte_array = np.packbits(self.rx_bits_array[:complete_bit_count]).tobytes()
        decoded = byte_array.decode("utf-8", errors="replace")
        hex_text = " ".join("{:02X}".format(value) for value in byte_array)
        self.received_text.setPlainText(decoded)
        self.received_hex.setPlainText(hex_text)
        preview = decoded.replace("\n", " ").strip() or "已接收二进制数据"
        self.control_rx_preview.setText(preview[:160])
        self.hex_preview_label.setText(hex_text[-180:] if hex_text else "--")

    def _refresh_plot(self) -> None:
        if self._waveform_cache is None:
            self.canvas.draw_placeholder()
            self.rx_canvas.draw_placeholder()
            return
        config, tx, rx = self._waveform_cache
        self.canvas.update_plots(config, tx, rx, self.ber_history)
        self.rx_canvas.update_waveform(config, rx)
        self.rx_wave_info.setText(
            "模拟后端 · 本次实验缓存 · {} 个采样点 · Fs {:.1f} MHz".format(
                rx.size, config.sample_rate_mhz
            )
        )

    def _record_result(self) -> None:
        if self._session_id in self._recorded_session_ids:
            return
        row = {
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "mode": self.config.work_mode,
            "channel": self.config.channel_mode,
            "snr_db": self.config.snr_db,
            "tx_bits": self.stats.tx_bits,
            "error_bits": self.stats.error_bits,
            "ber_percent": self.stats.ber * 100.0,
            "frames": self.stats.processed_frames,
            "planned_frames": self.stats.total_frames,
            "status": self.run_state,
            "termination_reason": self.termination_reason,
            "session_id": self._session_id,
            "elapsed_seconds": self.stats.elapsed_seconds,
            "rx_bits": self.stats.rx_bits,
            "correct_frames": self.stats.correct_frames,
            "error_frames": self.stats.error_frames,
            "lost_frames": self.stats.lost_frames,
            "unprocessed_frames": self.stats.unprocessed_frames,
        }
        row.update(asdict(self.config))
        self._recorded_session_ids.add(self._session_id)
        self.experiment_rows.append(row)
        row_index = self.result_table.rowCount()
        self.result_table.insertRow(row_index)
        values = [
            row["time"],
            self._state_text(),
            row["mode"],
            row["channel"],
            "{:.2f}".format(row["snr_db"]),
            str(row["tx_bits"]),
            str(row["error_bits"]),
            "{:.6f}".format(row["ber_percent"]),
            str(row["frames"]),
        ]
        for column, value in enumerate(values):
            item = QTableWidgetItem(value)
            item.setToolTip("{} · 已处理 {}/{} 帧；未处理 {} 帧".format(
                self._state_text(), self.stats.processed_frames,
                self.stats.total_frames, self.stats.unprocessed_frames,
            ))
            self.result_table.setItem(row_index, column, item)
        self.record_summary.setText("共 {} 条实验记录".format(len(self.experiment_rows)))

    def _browse_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择发送文件")
        if path:
            self.file_path_edit.setText(path)
            self.source_combo.setCurrentText("本地文件")

    def _clear_received_display(self) -> None:
        self.received_text.clear()
        self.received_hex.clear()
        self.hex_preview_label.setText("--")
        self.control_rx_preview.setText("等待接收数据……")

    def _export_csv(self) -> None:
        if not self.experiment_rows:
            QMessageBox.information(self, "没有数据", "请至少完成一次模拟实验。")
            return
        default_name = "experiment_{}.csv".format(datetime.now().strftime("%Y%m%d_%H%M%S"))
        path, _ = QFileDialog.getSaveFileName(self, "导出实验数据", default_name, "CSV (*.csv)")
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8-sig") as file:
            writer = csv.DictWriter(file, fieldnames=list(self.experiment_rows[0].keys()))
            writer.writeheader()
            writer.writerows(self.experiment_rows)
        self.log("实验数据已导出：{}".format(path))

    def _export_image(self) -> None:
        default_name = "signal_analysis_{}.png".format(datetime.now().strftime("%Y%m%d_%H%M%S"))
        path, _ = QFileDialog.getSaveFileName(self, "保存分析图", default_name, "PNG (*.png)")
        if path:
            self.canvas.figure.savefig(path, dpi=180, facecolor=self.canvas.figure.get_facecolor())
            self.log("分析图已保存：{}".format(path))

    def _export_log(self) -> None:
        default_name = "upper_computer_{}.txt".format(datetime.now().strftime("%Y%m%d_%H%M%S"))
        path, _ = QFileDialog.getSaveFileName(self, "导出日志", default_name, "Text (*.txt)")
        if path:
            Path(path).write_text(self.log_edit.toPlainText(), encoding="utf-8")

    def log(self, message: str, level: str = "INFO") -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_message.emit("[{}] [{:<7}] {}".format(timestamp, level, message))

    def _append_log(self, text: str) -> None:
        self.log_edit.appendPlainText(text)
        if self._session_id and not self._session_saved:
            self._session_log_lines.append(text)

    def _mode_changed(self, text: str) -> None:
        if self.running:
            return
        self.mode_badge.setText("● {}".format(text))
        self.analysis_hint.setText("当前数据源：{}".format(text))
        if text != "模拟模式":
            self.log("已选择{}，接口暂未实现。".format(text), "WARNING")
        self._refresh_all()

    def _channel_changed(self, text: str) -> None:
        if self.running:
            return
        self.nakagami_spin.setEnabled("Nakagami" in text)
        self._refresh_all()

    def _source_changed(self, text: str) -> None:
        if self.running:
            return
        self.payload_edit.setEnabled(text == "文本输入")
        self.random_bytes_spin.setEnabled(text == "随机字节")
        self.file_path_edit.setEnabled(text == "本地文件")
        self.browse_btn.setEnabled(text == "本地文件")

    def _update_clock(self) -> None:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.clock_label.setText(now)
        self.top_clock_label.setText(now)

    def _update_top_title(self, row: int) -> None:
        titles = [
            "通信链路总览", "收发任务配置", "接收实时监视", "信号性能分析",
            "实验数据记录", "系统运行日志", "专业术语说明",
        ]
        if 0 <= row < len(titles):
            self.top_title.setText(titles[row])

    def _toggle_advanced(self, checked: bool) -> None:
        self.advanced_panel.setVisible(checked)
        self.advanced_toggle.setText("高级参数   ⌄" if checked else "高级参数   ›")

    def _toggle_rx_view(self, index: int) -> None:
        self.received_text.setVisible(index == 0)
        self.received_hex.setVisible(index == 1)

    def _apply_preset(self, name: str) -> None:
        if self.running:
            return
        self._update_preset_actions()
        if name == "自定义":
            return
        if self.preset_combo.currentData() == "built-in":
            self._apply_config_values(BUILT_IN_PRESETS.get(name, {}))
        elif self.preset_combo.currentData() == "custom":
            self._apply_config_values(self.custom_presets.get(name, {}))
        else:
            return
        self.log("已应用场景预设：{}。".format(name))
        self._refresh_all()

    def _apply_style(self) -> None:
        tokens = dict(THEME)
        tokens.update(UI_METRICS)
        tokens["ui_font_family"] = UI_FONT_FALLBACK
        style_sheet = (
            """
            QMainWindow {
                background-color: %(bg_main)s;
                color: %(text_primary)s;
                font-family: %(ui_font_family)s;
                font-size: 16px;
            }
            QWidget, QToolTip {
                font-family: %(ui_font_family)s;
                font-size: 16px;
            }
            QWidget#appRoot, QWidget#contentRoot, QWidget#pageRoot,
            QWidget#settingsWidget, QStackedWidget#pageStack {
                background-color: %(bg_main)s;
                color: %(text_primary)s;
            }

            /* 纯文本继承父容器视觉背景，不再形成独立黑色矩形。 */
            QLabel {
                background-color: transparent;
                border: none;
                color: %(text_primary)s;
            }

            QFrame#sidebar {
                background-color: %(bg_sidebar)s;
                border: none;
                border-right: 1px solid %(border_soft)s;
            }
            QLabel#brand {
                color: %(accent)s;
                font-size: 26px;
                font-weight: 600;
                letter-spacing: 2px;
            }
            QLabel#brandSub { color: %(text_secondary)s; font-size: 14px; }
            QLabel#modeBadge {
                color: %(success)s;
                background-color: #14251F;
                border: 1px solid #28513F;
                border-radius: 8px;
                padding: 8px 12px;
                font-size: 16px;
            }
            QListWidget#nav {
                background-color: transparent;
                border: none;
                outline: none;
                color: %(text_secondary)s;
            }
            QListWidget#nav::item {
                height: 22px;
                padding: 10px 12px;
                border-radius: 8px;
                color: %(text_secondary)s;
                font-size: 16px;
            }
            QListWidget#nav::item:selected {
                background-color: %(accent_muted)s;
                color: %(text_primary)s;
            }
            QListWidget#nav::item:selected:active {
                border: 1px solid %(accent)s;
            }
            QListWidget#nav::item:hover:!selected {
                background-color: #162532;
                color: #C6D3DE;
            }

            QFrame#topStrip {
                background-color: %(bg_topbar)s;
                border: none;
                border-bottom: 1px solid %(border_soft)s;
            }
            QLabel#topTitle { color: %(text_primary)s; font-size: 20px; font-weight: 500; }
            QLabel#topClock { color: %(text_secondary)s; font-family: %(ui_font_family)s; font-size: 14px; }
            QFrame#statusPill {
                background-color: %(bg_card)s;
                border: 1px solid %(border_soft)s;
                border-radius: 12px;
            }
            QLabel#statusName { color: %(text_secondary)s; font-size: 14px; }
            QLabel#statusValue { color: %(success)s; font-size: 15px; font-weight: 500; }

            QLabel#pageTitle { color: %(text_primary)s; font-size: 28px; font-weight: 500; }
            QLabel#pageDesc { color: %(text_secondary)s; font-size: 16px; }
            QLabel#formLabel, QLabel#cardTitle, QLabel#hintLabel {
                color: %(text_secondary)s;
                font-size: 15px;
            }
            QLabel#valueText { color: %(text_primary)s; font-size: 16px; font-weight: 500; }

            QFrame#heroPanel {
                background-color: %(bg_card_alt)s;
                border: 1px solid #28506A;
                border-radius: 12px;
            }
            QLabel#heroStatus { color: #73C6FF; font-size: 23px; font-weight: 500; }
            QLabel#heroDetail { color: #A8B7C4; font-size: 16px; }
            QFrame#sectionPanel {
                background-color: %(bg_card)s;
                border: 1px solid %(border_soft)s;
                border-radius: 10px;
            }
            QLabel#sectionTitle { color: %(text_primary)s; font-size: 19px; font-weight: 500; }

            QFrame#flowNode {
                background-color: %(bg_card_alt)s;
                border: 1px solid %(border)s;
                border-radius: 9px;
            }
            QFrame#flowNode[state="active"] {
                background-color: #143044;
                border: 1px solid %(accent)s;
            }
            QFrame#flowNode[state="done"] {
                background-color: #142820;
                border: 1px solid #3C8B68;
            }
            QFrame#flowNode[state="warning"] {
                background-color: #2A2419;
                border: 1px solid %(warning)s;
            }
            QLabel#flowNumber { color: %(accent)s; font-size: 20px; font-weight: 500; }
            QLabel#flowTitle { color: %(text_primary)s; font-size: 16px; font-weight: 500; }
            QLabel#flowSubtitle { color: %(text_secondary)s; font-size: 14px; }
            QLabel#flowArrow { color: #49697F; font-size: 21px; }

            QFrame#metricCard, QFrame#smallCard {
                background-color: %(bg_card)s;
                border: 1px solid %(border_soft)s;
                border-radius: 10px;
            }
            QLabel#cardValue { font-size: 28px; font-weight: 500; }
            QLabel#cardUnit {
                color: %(text_secondary)s;
                font-size: 14px;
                padding-top: 7px;
            }
            QLabel#smallValue { color: %(text_primary)s; font-size: 21px; font-weight: 500; }
            QFrame#metricStrip {
                background-color: %(bg_card)s;
                border: 1px solid %(border_soft)s;
                border-radius: 10px;
            }
            QFrame#returnPanel {
                background-color: #12251F;
                border: 1px solid #28513F;
                border-radius: 9px;
            }
            QLabel#statusGood { color: %(success)s; font-weight: 500; }
            QLabel#rxPreview { color: #B9C8D4; font-family: %(ui_font_family)s; }
            QLabel#monoPreview {
                color: #91C9F0;
                background-color: %(bg_input)s;
                border: 1px solid %(border_soft)s;
                border-radius: 6px;
                padding: 8px;
                font-family: %(ui_font_family)s;
                font-size: 16px;
            }

            QGroupBox {
                background-color: %(bg_card)s;
                border: 1px solid %(border_soft)s;
                border-radius: 9px;
                margin-top: 12px;
                padding: 16px 12px 12px 12px;
                color: %(text_primary)s;
                font-weight: 500;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 4px; }

            QPushButton {
                min-height: 20px;
                background-color: #182631;
                border: 1px solid %(border)s;
                border-radius: 7px;
                padding: 8px 16px;
                color: #D7E1E9;
                font-size: 16px;
            }
            QPushButton:hover { background-color: #203442; border-color: #42657C; }
            QPushButton:pressed { background-color: #14212B; border-color: #35566B; }
            QPushButton:focus { border: 2px solid %(accent)s; padding: 7px 15px; }
            QPushButton:disabled {
                color: %(text_disabled)s;
                background-color: #121A21;
                border-color: #202C35;
            }
            QPushButton#primaryButton {
                background-color: #167EC2;
                border-color: %(accent)s;
                color: #F5FAFD;
                font-weight: 500;
            }
            QPushButton#primaryButton:hover { background-color: #1D8ED7; }
            QPushButton#primaryButton:pressed { background-color: #126BA6; }
            QPushButton#ghostButton { background-color: transparent; border-color: %(border)s; }
            QPushButton#ghostButton:hover { background-color: #182631; }

            QToolButton#sectionToggle {
                background-color: %(bg_card)s;
                border: 1px solid %(border_soft)s;
                border-radius: 7px;
                padding: 8px 12px;
                text-align: left;
                color: #C7D3DD;
                font-weight: 500;
            }
            QToolButton#sectionToggle:hover { background-color: #182631; border-color: %(border)s; }
            QToolButton#sectionToggle:focus { border: 2px solid %(accent)s; padding: 7px 11px; }

            QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit, QPlainTextEdit, QTableWidget {
                background-color: %(bg_input)s;
                border: 1px solid %(border)s;
                border-radius: 6px;
                padding: 6px;
                color: %(text_primary)s;
                selection-background-color: #1D6F9F;
                font-size: 16px;
            }
            QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus,
            QLineEdit:focus, QPlainTextEdit:focus, QTableWidget:focus {
                border: 2px solid %(accent)s;
                padding: 5px;
            }
            QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled,
            QLineEdit:disabled, QPlainTextEdit:disabled {
                color: %(text_disabled)s;
                background-color: #10171E;
                border-color: #21313D;
            }
            QComboBox QAbstractItemView {
                background-color: #101A22;
                color: %(text_primary)s;
                border: 1px solid %(border)s;
                outline: none;
                selection-background-color: #1F5F83;
                selection-color: #F2F8FC;
            }
            QComboBox QAbstractItemView::item {
                min-height: 28px;
                padding: 6px 10px;
                color: #DCE7EF;
                background-color: #101A22;
            }
            QComboBox QAbstractItemView::item:hover {
                color: #F4FAFE;
                background-color: #173044;
            }
            QComboBox QAbstractItemView::item:selected {
                color: #FFFFFF;
                background-color: #1F5F83;
            }
            QComboBox QAbstractItemView::item:disabled {
                color: #687984;
                background-color: #101A22;
            }
            QCheckBox { color: %(text_secondary)s; spacing: 8px; }
            QCheckBox:disabled { color: %(text_disabled)s; }
            QScrollArea#settingsScroll, QScrollArea#flowScroll {
                border: none;
                background-color: transparent;
            }
            QWidget#flowContent { background-color: transparent; }

            QListWidget#recentFrames {
                background-color: %(bg_input)s;
                border: 1px solid %(border_soft)s;
                border-radius: 7px;
                padding: 4px;
                color: #C8D4DE;
            }
            QListWidget#recentFrames::item { padding: 6px; border-bottom: 1px solid #1E2D38; }
            QListWidget#recentFrames::item:alternate { background-color: #101A22; }

            QProgressBar {
                min-height: 20px;
                background-color: %(bg_input)s;
                border: 1px solid %(border_soft)s;
                border-radius: 6px;
                text-align: center;
                color: #C9D6E0;
            }
            QProgressBar::chunk { background-color: #238FD0; border-radius: 5px; }

            QHeaderView::section {
                background-color: #17242E;
                color: #C3D0DA;
                padding: 8px;
                border: none;
                border-right: 1px solid %(border_soft)s;
                border-bottom: 1px solid %(border_soft)s;
            }
            QTableWidget { gridline-color: #22323E; alternate-background-color: #101922; }
            QTableWidget::item { padding: 5px; }
            QTableWidget::item:selected { background-color: %(accent_muted)s; color: %(text_primary)s; }
            QPlainTextEdit#logEdit { font-family: %(ui_font_family)s; font-size: 16px; }

            QScrollBar:vertical {
                background: transparent;
                width: 10px;
                margin: 2px;
            }
            QScrollBar::handle:vertical {
                background: #2A3F4F;
                min-height: 28px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical:hover { background: #38556A; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
            QScrollBar:horizontal {
                background: transparent;
                height: 10px;
                margin: 2px;
            }
            QScrollBar::handle:horizontal {
                background: #2A3F4F;
                min-width: 28px;
                border-radius: 4px;
            }
            QScrollBar::handle:horizontal:hover { background: #38556A; }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

            QStatusBar {
                background-color: %(bg_topbar)s;
                color: %(text_secondary)s;
                border-top: 1px solid %(border_soft)s;
                font-size: 14px;
            }
            QStatusBar QLabel { color: %(text_secondary)s; }

            /* V0.9 科技仪器主题：保持已有字号，统一交互状态。 */
            QFrame#sidebar, QFrame#topStrip { background: %(bg_sidebar)s; }
            QLabel#brand { color: %(accent)s; font-size: 23px; font-weight: 500; }
            QLabel#brandSub { color: %(text_secondary)s; font-size: 14px; }
            QFrame#sectionPanel, QFrame#metricStrip, QFrame#metricCard {
                background: %(bg_panel)s; border: 1px solid %(border_subtle)s; border-radius: 12px;
            }
            QFrame#returnPanel { background: %(bg_panel_raised)s; border-color: %(divider)s; }
            QLabel#rxMetricValue { color: %(text_primary)s; font-size: 21px; font-weight: 400; }
            QLabel#rxMetricValue[accent="true"] { color: %(accent)s; font-weight: 500; }
            QLabel#hintLabel { color: %(text_secondary)s; font-size: 14px; font-weight: 400; }
            QLabel#sectionTitle { font-weight: 500; }
            QListWidget#nav::item { border-radius: 8px; color: %(text_secondary)s; }
            QListWidget#nav::item:selected { background: %(bg_selected)s; color: %(text_primary)s; border-color: %(border_focus)s; }
            QPushButton { border-radius: 7px; background: %(bg_panel_raised)s; font-weight: 400; padding: 6px 12px; }
            QPushButton:hover { background: %(bg_hover)s; border-color: %(border_focus)s; }
            QPushButton:focus { border: 2px solid %(border_focus)s; padding: 5px 11px; }
            QPushButton#primaryButton { background: #2563D9; color: #FFFFFF; border-color: #2563D9; font-weight: 500; }
            QPushButton#primaryButton:hover { background: #3475E7; }
            QPushButton#primaryButton:pressed { background: #1D50B3; }
            QPushButton#dangerButton { color: %(danger)s; background: transparent; border-color: %(danger)s; }
            QToolButton#pageTermHelp {
                color: %(accent)s; background: %(bg_panel_raised)s;
                border: 1px solid %(border_subtle)s; border-radius: 6px;
                padding: 5px 10px; font-size: 13px;
            }
            QToolButton#pageTermHelp:hover { background: %(bg_hover)s; border-color: %(border_focus)s; }
            QToolButton#pageTermHelp:focus { border: 2px solid %(border_focus)s; padding: 4px 9px; }
            QPushButton#primaryButton:disabled, QPushButton#dangerButton:disabled, QPushButton:disabled {
                background: %(bg_input)s; color: %(text_disabled)s; border-color: %(border_subtle)s;
            }
            QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit {
                background: %(bg_input)s; color: %(text_primary)s;
                border: 1px solid %(border_strong)s; border-radius: 6px; padding: 6px;
            }
            QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover, QLineEdit:hover { border-color: %(border_focus)s; }
            QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QLineEdit:focus { border: 2px solid %(border_focus)s; padding: 5px; }
            QComboBox QAbstractItemView { background: %(bg_panel)s; color: %(text_primary)s; selection-background-color: %(bg_selected)s; selection-color: #FFFFFF; }
            QComboBox QAbstractItemView::item { background: %(bg_panel)s; color: %(text_primary)s; min-height: 28px; }
            QComboBox QAbstractItemView::item:hover { background: %(bg_hover)s; color: #FFFFFF; }
            QComboBox QAbstractItemView::item:selected { background: %(bg_selected)s; color: #FFFFFF; }
            QComboBox QAbstractItemView::item:disabled { color: %(text_disabled)s; background: %(bg_input)s; }
            QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QLineEdit:disabled {
                color: %(text_disabled)s; border-color: %(border_subtle)s; background: %(bg_input)s;
            }
            QPlainTextEdit, QListWidget#recentFrames { background: %(bg_input)s; color: %(text_primary)s; border-color: %(divider)s; }
            QListWidget#recentFrames::item { padding: 4px 8px; min-height: 20px; }
            QLabel#monoPreview { color: %(accent)s; background: %(bg_input)s; border-color: %(divider)s; font-size: 14px; }
            QProgressBar { background: %(bg_input)s; border: 1px solid %(divider)s; border-radius: 4px; text-align: center; color: %(text_primary)s; }
            QProgressBar::chunk { background: #2563D9; border-radius: 3px; }
            QSplitter#rxSplitter::handle { background: transparent; }
            QSplitter#rxSplitter::handle:hover { background: %(divider)s; }
            QToolTip { color: %(text_primary)s; background: %(bg_panel_raised)s; border: 1px solid %(border_strong)s; padding: 6px; }
            """ % tokens
        )
        self.setStyleSheet(style_sheet)



def main() -> int:
    if hasattr(Qt, "AA_EnableHighDpiScaling"):
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    if hasattr(Qt, "AA_UseHighDpiPixmaps"):
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName(APP_TITLE)
    app.setApplicationVersion(APP_VERSION)
    font = QFont(UI_FONT_FAMILY, 12)
    font.setWeight(QFont.Normal)
    app.setFont(font)
    window = MainWindow()
    window.show()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
