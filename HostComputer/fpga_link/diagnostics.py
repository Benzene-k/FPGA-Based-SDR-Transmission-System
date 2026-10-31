import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from time import monotonic

from .serial_client import LinkError


def checked_ping(client):
    info = client.ping(timeout=0.5, retries=0)
    if not info.comm_only:
        raise LinkError('设备未标记为仅通信固件，请确认下载的程序')
    return info


def run_ping_test(client, count, cancel, progress=None):
    if type(count) is not int or not 1 <= count <= 10000:
        raise ValueError('PING count must be an integer from 1 to 10000')
    started = monotonic()
    report = {'planned': count, 'attempted': 0, 'passed': 0, 'failed': 0,
              'status': 'running', 'error': '', 'started_at': datetime.now().isoformat(timespec='seconds'),
              'elapsed_seconds': 0.0, 'rtt_ms': {'min': None, 'mean': None, 'max': None}}
    info, samples, total_ms = None, [], 0.0
    decoder = getattr(client, 'decoder', None)
    before = {name: getattr(decoder, name, None) for name in ('crc_errors', 'length_errors')}
    for _ in range(count):
        if cancel.is_set():
            break
        report['attempted'] += 1
        request_start = monotonic()
        try:
            info = checked_ping(client)
        except Exception as exc:
            report['failed'] += 1
            report['error'] = str(exc)
            break
        elapsed_ms = (monotonic() - request_start) * 1000
        samples.append(elapsed_ms)
        total_ms += elapsed_ms
        report['passed'] += 1
        rtt = report['rtt_ms']
        report['rtt_ms'] = {'min': elapsed_ms if rtt['min'] is None else min(rtt['min'], elapsed_ms),
                            'mean': total_ms / len(samples),
                            'max': elapsed_ms if rtt['max'] is None else max(rtt['max'], elapsed_ms)}
        report['elapsed_seconds'] = monotonic() - started
        if progress is not None:
            progress(dict(report))
    report['status'] = 'failed' if report['failed'] else ('passed' if report['passed'] == count else 'cancelled')
    report['elapsed_seconds'] = monotonic() - started
    report['latency_ms'] = samples
    report['decoder_delta'] = {name: None if value is None else getattr(decoder, name) - value
                               for name, value in before.items()}
    return info, report


def save_diagnostics(path, report):
    destination = Path(path)
    contents = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=str(destination.parent),
                                         prefix=destination.name + '.', suffix='.pending', delete=False) as output:
            temporary = Path(output.name)
            output.write(contents)
        os.replace(str(temporary), str(destination))
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
