import hashlib
import os
from pathlib import Path
from time import monotonic
from datetime import datetime
from .protocol import MAX_PAYLOAD


def run_file_echo(client, path, cancel, progress=None, timeout=0.5):
    started = monotonic()
    report = dict(kind='file_echo', path=str(path), status='running', total_bytes=0,
                  verified_bytes=0, chunks_passed=0, chunks_attempted=0, error='',
                  error_source=None, whole_file_verified=False,
                  source_sha256=None, received_sha256=None,
                  automatic_retries=0, elapsed_seconds=0.0,
                  started_at=datetime.now().isoformat(timespec='seconds'))
    sent_hash, received_hash = hashlib.sha256(), hashlib.sha256()

    def signature(stat):
        return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns

    def publish():
        report['elapsed_seconds'] = monotonic() - started
        if progress:
            progress(dict(report))

    phase = 'file'
    try:
        with Path(path).open('rb') as source:
            initial = os.fstat(source.fileno())
            report['total_bytes'] = initial.st_size
            first = True
            while report['verified_bytes'] < initial.st_size or first:
                if cancel.is_set():
                    report['status'] = 'cancelled'
                    break
                first = False
                phase = 'file'
                payload = source.read(min(MAX_PAYLOAD, initial.st_size - report['verified_bytes']))
                if not payload and initial.st_size:
                    raise ValueError('Source file truncated during transfer')
                report['chunks_attempted'] += 1
                phase = 'transport'
                received = client.echo(payload, timeout=timeout)
                phase = 'integrity'
                if received != payload:
                    raise ValueError('Echo payload mismatch at byte {}'.format(report['verified_bytes']))
                phase = 'internal'
                sent_hash.update(payload)
                received_hash.update(received)
                report['verified_bytes'] += len(payload)
                report['chunks_passed'] += 1
                publish()
            phase = 'file'
            if signature(os.fstat(source.fileno())) != signature(initial) or signature(Path(path).stat()) != signature(initial):
                raise ValueError('Source file changed during transfer')
        if report['status'] != 'cancelled':
            phase = 'integrity'
            if report['verified_bytes'] != initial.st_size or sent_hash.digest() != received_hash.digest():
                raise ValueError('Whole-file verification incomplete or hash mismatch')
            report['source_sha256'] = sent_hash.hexdigest()
            report['received_sha256'] = received_hash.hexdigest()
            report['whole_file_verified'] = True
            report['status'] = 'passed'
    except Exception as exc:
        report['status'], report['error'] = 'failed', str(exc)
        report['error_source'] = phase
        report['whole_file_verified'] = False
        report['source_sha256'] = report['received_sha256'] = None
    report['verified_prefix_source_sha256'] = sent_hash.hexdigest()
    report['verified_prefix_received_sha256'] = received_hash.hexdigest()
    publish()
    return report
