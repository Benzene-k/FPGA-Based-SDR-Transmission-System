import os
import tempfile
from pathlib import Path

from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg
import numpy as np

from .analysis import spectrum


def export_png(snapshot, path, mode='time', time_axis=False, window='hann', remove_dc=True):
    path = Path(path)
    if path.suffix.lower() != '.png' or mode not in ('time', 'spectrum'):
        raise ValueError('请选择 PNG 文件和时域/频谱视图。')
    figure = Figure(figsize=(10, 5.8), dpi=150, constrained_layout=True)
    FigureCanvasAgg(figure)
    ax = figure.subplots()
    if mode == 'spectrum':
        result = spectrum(snapshot, window, remove_dc)
        ax.plot(result['frequency'], result['amplitude'], linewidth=1)
        ax.set_xlabel('Frequency / Hz (configured sample rate)')
        ax.set_ylabel('Single-sided peak amplitude / code')
        detail = 'window={} | remove_dc={}'.format(window, remove_dc)
    else:
        x = np.arange(len(snapshot.samples))
        if time_axis:
            x = x / snapshot.config.sample_rate
        ax.plot(x, snapshot.samples, linewidth=1)
        ax.set_xlabel('Time / s (configured sample rate)' if time_axis else 'Sample index')
        ax.set_ylabel('Raw code (8 effective bits)')
        ax.set_ylim(-5, 260)
        detail = 'full snapshot | no voltage calibration'
    source = snapshot.source
    if snapshot.import_info:
        source += ' (declared origin: {}; not hardware verified)'.format(snapshot.import_info.declared_source)
    description = '{} | {} | {}\nID={}\n{} | N={}/{} | Fs={} Sa/s (configured)\n{}'.format(
        mode, source, snapshot.status, snapshot.snapshot_id, snapshot.created_at,
        len(snapshot.samples), snapshot.config.count, snapshot.config.sample_rate, detail)
    wave = snapshot.config.wave
    description += '\nwave={} | configured f={} Hz | amplitude={} code | offset={} code'.format(
        wave.kind, wave.frequency if wave.kind == 'sine' else 'N/A',
        wave.amplitude if wave.kind == 'sine' else 'N/A', wave.offset if wave.kind != 'ramp' else 'N/A')
    ax.set_title(description, fontsize=9)
    if snapshot.digital_info:
        info = snapshot.digital_info
        description += '\nsession={:08X} | capture={} | CRC32={} | rate basis={}'.format(
            info.session, info.capture_id, 'verified' if info.verified else 'unverified', info.rate_basis)
        ax.set_title(description, fontsize=8)
    ax.grid(alpha=0.3)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=str(path.parent), prefix='.adda_png_', suffix='.png', delete=False) as stream:
            temporary = Path(stream.name)
        figure.savefig(str(temporary), format='png', metadata={'Description': description})
        os.replace(str(temporary), str(path))
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
        figure.clear()
    return path
