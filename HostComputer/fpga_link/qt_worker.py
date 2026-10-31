from time import monotonic
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot
from .diagnostics import checked_ping, run_ping_test
from .file_echo import run_file_echo
from .protocol import Message
from .serial_client import LinkError


class LinkWorker(QObject):
    completed = pyqtSignal(str, object)
    failed = pyqtSignal(str, str)
    progress = pyqtSignal(object)
    stopped = pyqtSignal()
    file_progress = pyqtSignal(object)
    digital_progress = pyqtSignal(object)
    digital_failed = pyqtSignal(object)
    rf_failed = pyqtSignal(object)

    def __init__(self, client_factory):
        super().__init__()
        self.client_factory = client_factory
        self.client = None
        self.rf_service = None

    @pyqtSlot(str, object)
    def execute(self, operation, payload):
        started = monotonic()
        try:
            if operation == 'shutdown':
                self._close()
                return
            if operation == 'disconnect':
                self._close()
                self.completed.emit(operation, None)
                return
            if operation == 'connect':
                self._close()
                self.client = self.client_factory()
                self.client.open(payload, 115200)
            if self.client is None:
                raise LinkError('串口未连接')
            if operation.startswith('RF_'):
                self._execute_rf(operation, payload)
                return
            if operation.startswith('DIGITAL_'):
                self._execute_digital(operation, payload)
                return
            if operation == 'batch':
                last_update = [started]
                def report_progress(report):
                    now = monotonic()
                    if report['attempted'] == 1 or now - last_update[0] >= 0.05:
                        self.progress.emit(report)
                        last_update[0] = now
                info, report = run_ping_test(self.client, payload['count'], payload['cancel'], report_progress)
                if report['status'] == 'failed':
                    try:
                        self._close()
                    except Exception as exc:
                        report['error'] += '；关闭串口失败：' + str(exc)
                self.completed.emit(operation, (info, (monotonic() - started) * 1000, report))
                return
            if operation in ('CONFIG_GET', 'CONFIG_SET'):
                if operation == 'CONFIG_SET':
                    self.client.set_config(payload, timeout=0.5)
                config = self.client.get_config(timeout=0.5)
                if operation == 'CONFIG_SET' and config != payload:
                    raise LinkError('Independent configuration readback mismatch; stored result unknown')
                self.completed.emit(operation, (config, (monotonic() - started) * 1000))
                return
            if operation == 'FILE':
                last_update = [started]
                def file_progress(report):
                    now = monotonic()
                    if report['status'] != 'running' or now - last_update[0] >= 0.05:
                        self.file_progress.emit(report)
                        last_update[0] = now
                report = run_file_echo(self.client, payload['path'], payload['cancel'], file_progress)
                if report['status'] == 'failed' and report.get('error_source') != 'file':
                    try:
                        self._close()
                    except Exception as exc:
                        report['error'] += '; close failed: ' + str(exc)
                self.completed.emit(operation, report)
                return
            if operation == 'ECHO':
                received = self.client.echo(payload, timeout=0.5)
                self.completed.emit(operation, (received, (monotonic() - started) * 1000))
                return
            ack = None
            if operation in ('START', 'STOP', 'RESET'):
                ack = self.client.control(Message[operation], timeout=0.5)
            info = checked_ping(self.client)
            if ack is not None and (ack != (operation == 'START') or info.requested_running != ack):
                raise LinkError('ACK 与查询状态不一致')
            self.completed.emit(operation, (info, (monotonic() - started) * 1000))
        except Exception as exc:
            message = str(exc)
            try:
                self._close()
            except Exception as close_error:
                message += '；关闭串口失败：' + str(close_error)
            self.failed.emit(operation, message)
        finally:
            if operation == 'shutdown':
                self.stopped.emit()

    def _close(self):
        self.rf_service = None
        if self.client is not None:
            client, self.client = self.client, None
            client.close()

    def _execute_rf(self, operation, payload):
        from .rf_service import RfService
        from .serial_client import RemoteError
        from adda.digital.client import DigitalError
        if self.rf_service is None:
            self.rf_service = RfService(self.client)
        try:
            result = self.rf_service.execute(operation, payload)
        except Exception as exc:
            fatal = not isinstance(exc, (ValueError, OSError, RemoteError))
            if isinstance(exc, DigitalError):
                fatal = exc.code is None
            report = dict(operation=operation, error=str(exc), fatal=fatal,
                          result=self.rf_service.partial_result)
            self.rf_service.session = None
            if fatal:
                self._close()
            self.rf_failed.emit(report)
            return
        self.completed.emit(operation, result)

    def _execute_digital(self, operation, payload):
        from adda.digital.client import DigitalClient, DigitalError
        from adda.digital.transport import SerialExchange
        from adda.digital.protocol import COUNTS, Source
        try:
            payload = dict(payload)
            timeout = payload.get('timeout',0.5)
            if type(timeout) not in (int,float) or not 0 < timeout <= 5:
                raise ValueError('数字采样超时须为 0～5 秒范围内的正数')
            if operation == 'DIGITAL_CAPTURE':
                count, source, fixed = payload['count'],payload['source'],payload.get('fixed',0)
                if (type(count) is not int or count not in COUNTS or type(source) not in (int,Source)
                        or source not in tuple(Source) or type(fixed) is not int or not 0 <= fixed <= 255):
                    raise ValueError('数字采样点数、模式或固定码无效')
            elif operation in ('DIGITAL_STATUS','DIGITAL_CANCEL','DIGITAL_RELEASE'):
                if any(type(payload[name]) is not int or not 1 <= payload[name] <= 0xffffffff
                       for name in ('session','capture_id')):
                    raise ValueError('数字采样会话和任务 ID 无效')
            elif operation != 'DIGITAL_INFO':
                raise ValueError('未知数字采样任务：' + operation)
        except (KeyError,TypeError,ValueError) as exc:
            self.digital_failed.emit({'operation':operation,'source':'local','error':str(exc),
                                      'code':None,'partial':b''})
            return
        client = DigitalClient(SerialExchange(self.client, timeout))
        try:
            if operation == 'DIGITAL_INFO':
                result = client.info()
            elif operation == 'DIGITAL_CAPTURE':
                result = client.capture_read(payload['count'],payload['source'],payload.get('fixed',0),
                    cancel=payload.get('cancel'),
                    progress=lambda count:self.digital_progress.emit({'received':count,'planned':payload['count']}))
            elif operation in ('DIGITAL_STATUS','DIGITAL_CANCEL','DIGITAL_RELEASE'):
                action = {'DIGITAL_STATUS':client.status,'DIGITAL_CANCEL':client.cancel,
                          'DIGITAL_RELEASE':client.release}[operation]
                result = action(payload['session'],payload['capture_id'])
            else:
                raise ValueError('未知数字采样任务：' + operation)
        except DigitalError as exc:
            self.digital_failed.emit({'operation':operation,'source':'remote' if exc.code is not None else 'link', 'error':str(exc),
                                      'code':exc.code,'partial':exc.partial,
                                      'session':getattr(exc, 'session', 0), 'capture_id':getattr(exc, 'capture_id', 0)})
            if exc.code is not None:
                return
            raise
        self.completed.emit(operation, result)
