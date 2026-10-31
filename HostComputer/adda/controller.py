from dataclasses import dataclass
from threading import Event
from uuid import uuid4

from PyQt5.QtCore import QObject, QTimer, pyqtSignal

from .models import make_snapshot
from .sources import LocalTestSource


@dataclass(frozen=True)
class TaskReport:
    task_id: str
    status: str
    actual_count: int
    expected_count: int
    error: str = ''


class CaptureController(QObject):
    state_changed = pyqtSignal(str)
    progress = pyqtSignal(int)
    completed = pyqtSignal(object)

    def __init__(self, parent=None, source=None):
        super().__init__(parent)
        self.source = source or LocalTestSource()
        self.busy = self.closing = False
        self.current_snapshot = self.last_partial = self.last_report = None
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._step)

    def start(self, config):
        if self.busy or self.closing:
            return False
        config.validate()
        self._config = config
        self._task_id = str(uuid4())
        self._raw = bytearray()
        self._cancel = Event()
        self.last_partial = None
        self.busy = True
        self.state_changed.emit('生成中；当前图如有数据，仍为上次结果')
        try:
            self._chunks = iter(self.source.chunks(config, self._cancel))
        except Exception as exc:
            self._finish('failed', str(exc))
            return True
        self.progress.emit(0)
        self.timer.start(0)
        return True

    def cancel(self):
        if self.busy:
            self._cancel.set()
            self.state_changed.emit('取消中')

    def _step(self):
        if not self.busy:
            return
        if self._cancel.is_set():
            self._finish('cancelled')
            return
        try:
            chunk = next(self._chunks)
            if not isinstance(chunk, bytes) or not chunk or len(chunk) % 2:
                raise ValueError('数据源返回空块或未对齐的字节块。')
            make_snapshot(self._task_id, self._config, chunk, 'partial')
            if len(self._raw) + len(chunk) > self._config.count * 2:
                raise ValueError('数据源返回的点数超过配置。')
            self._raw.extend(chunk)
            self.progress.emit(len(self._raw) // 2)
            if self.busy:
                self.timer.start(0)
        except StopIteration:
            self.state_changed.emit('校验中')
            self._finish('complete')
        except Exception as exc:
            self._finish('failed', str(exc))

    def _finish(self, status, error=''):
        self.timer.stop()
        if status == 'complete' and self._cancel.is_set():
            status = 'cancelled'
        snapshot = None
        try:
            if self._raw:
                snapshot = make_snapshot(self._task_id, self._config, self._raw,
                                         'complete' if status == 'complete' else 'partial')
            elif status == 'complete':
                raise ValueError('数据源未返回数据。')
        except ValueError as exc:
            status, error = 'failed', str(exc)
            if self._raw:
                snapshot = make_snapshot(self._task_id, self._config, self._raw, 'partial')
        if status == 'complete':
            self.current_snapshot = snapshot
        else:
            self.last_partial = snapshot
        self.busy = False
        self.last_report = TaskReport(self._task_id, status, len(self._raw) // 2,
                                      self._config.count, error)
        self._chunks = None
        self._raw = None
        self.completed.emit(self.last_report)

    def shutdown(self):
        self.closing = True
        if self.busy:
            self._cancel.set()
            self._finish('cancelled')
        self.timer.stop()
