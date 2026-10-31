import csv
import json
import os
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

from .analysis import statistics


def metadata(snapshot):
    result = dict(schema_version=1, snapshot_id=snapshot.snapshot_id,
                task_id=snapshot.task_id, created_at=snapshot.created_at,
                source=snapshot.source, module='Imported package' if snapshot.import_info else 'PC local generator', channel=0,
                effective_bits=snapshot.effective_bits, encoding='unsigned_binary',
                alignment='right', storage='u16', byte_order='little',
                status=snapshot.status, expected_count=snapshot.config.count,
                actual_count=len(snapshot.samples), config=asdict(snapshot.config),
                generator_version=1, quantization='numpy.rint (ties to even)',
                time_axis_basis='configured_sample_rate', measured_sample_rate=None,
                device_session_id=None, device_capture_id=None, dac_association=None,
                checks=dict(code_range=True, u16_alignment=True,
                            complete_count=len(snapshot.samples) == snapshot.config.count,
                            whole_segment_pass=snapshot.status == 'complete'),
                raw_sha256=snapshot.raw_sha256,
                sha256_purpose='local exported raw-byte identity; not device verification',
                frame_crc={'availability': 'not_applicable', 'passed': None},
                segment_crc={'availability': 'not_applicable', 'passed': None},
                hardware={name: dict(availability='not_applicable', count=None)
                          for name in ('otr', 'capture_overflow')},
                statistics=statistics(snapshot))
    if snapshot.import_info:
        result['import_info'] = asdict(snapshot.import_info)
    if snapshot.digital_info:
        info = snapshot.digital_info
        result.update(module='FPGA internal digital test (not ADC)', generator_version=None,
                      quantization='8-bit internal codes stored as u16 little endian',
                      device_session_id=info.session, device_capture_id=info.capture_id,
                      digital_info=asdict(info),
                      segment_crc=dict(availability='crc32_ieee' if info.verified else 'unverified',
                                       passed=info.verified, value=info.crc32),
                      frame_crc=dict(availability='declared_by_import' if snapshot.import_info else 'crc16_ccitt',
                                     passed=None if snapshot.import_info else True))
    origin = snapshot.import_info.declared_source if snapshot.import_info else snapshot.source
    if origin == 'FPGA_EXTERNAL_ADC':
        result.update(module='ATK-MO8008 V3.3 external ADC (3PA9280)',
                      quantization='8-bit ADC raw codes stored as u16 little endian',
                      hardware={name: dict(availability='not_collected', count=None) for name in ('otr', 'capture_overflow')})
    return result


def export_snapshot(snapshot, parent):
    parent = Path(parent)
    token = uuid4().hex
    staging = parent / ('.adda_pending_' + token)
    target = parent / ('adda_' + snapshot.status + '_' + token[:12])
    staging.mkdir()
    names = ('samples.bin', 'samples.csv', 'metadata.json')
    try:
        (staging / names[0]).write_bytes(snapshot.raw)
        with (staging / names[1]).open('w', encoding='utf-8-sig', newline='') as stream:
            writer = csv.writer(stream)
            writer.writerow(('sample_index', 'time_s_configured', 'raw_code'))
            for index, code in enumerate(snapshot.samples):
                writer.writerow((index, format(index / snapshot.config.sample_rate, '.17g'), int(code)))
        (staging / names[2]).write_text(
            json.dumps(metadata(snapshot), ensure_ascii=False, indent=2, allow_nan=False),
            encoding='utf-8')
        os.replace(str(staging), str(target))
    except Exception:
        for name in names:
            try:
                (staging / name).unlink()
            except OSError:
                pass
        try:
            staging.rmdir()
        except OSError:
            pass
        raise
    return target
