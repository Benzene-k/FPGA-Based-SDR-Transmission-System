import csv
import io
import json
import math
from dataclasses import replace
from datetime import datetime, timezone, timedelta
from pathlib import Path
from uuid import uuid4

from .analysis import statistics
from .models import CaptureConfig, WaveConfig, ImportInfo, make_snapshot
from .models import DigitalInfo
import zlib


def _read(path, limit):
    with path.open('rb') as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError('数据包文件超过本版大小限制：' + path.name)
    return data


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('JSON 含重复字段：' + key)
        result[key] = value
    return result


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def _reject_constant(value):
    raise ValueError('JSON 含非有限值：' + value)


def _load(folder):
    meta = json.loads(_read(folder/'metadata.json', 65536).decode('utf-8-sig'),
                      object_pairs_hook=_unique_object,
                      parse_constant=_reject_constant)
    expected = dict(schema_version=1, effective_bits=8, channel=0, storage='u16',
                    encoding='unsigned_binary', alignment='right', byte_order='little',
                    time_axis_basis='configured_sample_rate')
    for key, value in expected.items():
        if type(meta[key]) is not type(value) or meta[key] != value:
            raise ValueError('不支持或不一致的元数据字段：' + key)
    declared = meta['source']
    if declared == 'FILE_IMPORT':
        declared = meta['import_info']['declared_source']
    external = declared == 'FPGA_EXTERNAL_ADC'
    digital = declared in ('FPGA_INTERNAL_DIGITAL_TEST', 'FPGA_EXTERNAL_ADC')
    if meta['source'] not in ('PC_LOCAL_TEST', 'FILE_IMPORT', 'FPGA_INTERNAL_DIGITAL_TEST', 'FPGA_EXTERNAL_ADC') or declared not in ('PC_LOCAL_TEST', 'FPGA_INTERNAL_DIGITAL_TEST', 'FPGA_EXTERNAL_ADC'):
        raise ValueError('不支持的原始来源声明。')
    for key in (('measured_sample_rate', 'dac_association') if digital else
                ('measured_sample_rate', 'device_session_id', 'device_capture_id', 'dac_association')):
        if meta[key] is not None:
            raise ValueError('本地数据包包含不支持的硬件记录：' + key)
    for key in (() if digital else ('frame_crc', 'segment_crc')):
        if meta[key] != dict(availability='not_applicable', passed=None):
            raise ValueError('本地数据包设备校验状态不符。')
    for key in ('otr', 'capture_overflow'):
        if meta['hardware'][key] != dict(availability='not_collected' if external else 'not_applicable', count=None):
            raise ValueError('本地数据包硬件指标不符。')
    for key in ('snapshot_id', 'task_id'):
        if not isinstance(meta[key], str) or not 1 <= len(meta[key]) <= 128:
            raise ValueError('快照或任务 ID 无效。')
    created = datetime.fromisoformat(meta['created_at'])
    if created.tzinfo is None:
        raise ValueError('快照时间缺少时区。')
    cfg = meta['config']
    if not _finite(cfg['sample_rate']):
        raise ValueError('配置采样率无效。')
    wave = cfg['wave']
    if not _finite(wave['frequency']):
        raise ValueError('波形频率无效。')
    config = CaptureConfig(cfg['count'], cfg['sample_rate'], WaveConfig(**wave))
    config.validate()
    if (type(meta['actual_count']) is not int or type(meta['expected_count']) is not int
            or meta['expected_count'] != config.count):
        raise ValueError('元数据点数类型或期望点数不符。')
    raw = _read(folder/'samples.bin', 8192)
    result = make_snapshot('import-' + str(uuid4()), config, raw, meta['status'])
    if len(result.samples) != meta['actual_count'] or result.raw_sha256 != meta['raw_sha256']:
        raise ValueError('BIN 点数或 SHA-256 与元数据不符。')
    if digital:
        evidence = DigitalInfo(**meta['digital_info'])
        if (any(type(v) is not int or not 1 <= v <= 0xffffffff for v in (evidence.session, evidence.capture_id))
                or evidence.session != meta['device_session_id'] or evidence.capture_id != meta['device_capture_id']
                or type(evidence.verified) is not bool or evidence.verified != (result.status == 'complete')
                or (evidence.rate_basis, evidence.sample_rate) not in (('test_image_nominal_50MHz_not_measured', None), ('firmware_declared_nominal_not_measured', 10000000), ('firmware_declared_nominal_not_measured', 25000000))
                or config.sample_rate != (evidence.sample_rate or 50e6)
                or (external and (evidence.sample_rate not in (10000000, 25000000) or config.wave.kind != 'external_adc'))
                or (not external and config.wave.kind not in ('ramp', 'fixed', 'walking'))
                or (evidence.verified and (type(evidence.crc32) is not int or evidence.crc32 != zlib.crc32(raw)))
                or (not evidence.verified and evidence.crc32 is not None)
                or meta['segment_crc'] != dict(availability='crc32_ieee' if evidence.verified else 'unverified',
                                               passed=evidence.verified, value=evidence.crc32)):
            raise ValueError('板内数字源记录与原始字节不一致。')
        result = replace(result, digital_info=evidence)
    actual_stats = statistics(result)
    for key, value in actual_stats.items():
        reported = meta['statistics'][key]
        if not _finite(reported) or not math.isclose(reported, value, rel_tol=1e-12, abs_tol=1e-12):
            raise ValueError('统计值与原始数据不一致：' + key)
    complete = len(result.samples) == config.count
    checks = dict(code_range=True, u16_alignment=True, complete_count=complete,
                  whole_segment_pass=meta['status'] == 'complete')
    if any(type(meta['checks'][key]) is not bool or meta['checks'][key] != value
           for key, value in checks.items()):
        raise ValueError('完整性标记与数据不一致。')
    reader = csv.DictReader(io.StringIO(_read(folder/'samples.csv', 1048576).decode('utf-8-sig')))
    if reader.fieldnames != ['sample_index', 'time_s_configured', 'raw_code']:
        raise ValueError('CSV 列名或顺序不支持。')
    for index, code in enumerate(result.samples):
        row = next(reader, None)
        if row is None:
            raise ValueError('CSV 与 BIN 点数不同。')
        time_value = float(row['time_s_configured'])
        if (None in row or int(row['sample_index']) != index or int(row['raw_code']) != int(code)
                or not math.isfinite(time_value)
                or not math.isclose(time_value, index / config.sample_rate, rel_tol=1e-12, abs_tol=1e-15)):
            raise ValueError('CSV 样本、索引或时间与 BIN/配置不同，第 {} 行。'.format(index + 2))
    if next(reader, None) is not None:
        raise ValueError('CSV 含超出 BIN 点数的额外行。')
    declared = meta['source']
    if declared == 'FILE_IMPORT':
        declared = meta['import_info']['declared_source']
    if declared not in ('PC_LOCAL_TEST', 'FPGA_INTERNAL_DIGITAL_TEST', 'FPGA_EXTERNAL_ADC'):
        raise ValueError('不支持的原始来源声明。')
    info = ImportInfo(str(folder.resolve()), datetime.now(timezone(timedelta(hours=8))).isoformat(),
                      declared, meta['snapshot_id'])
    return replace(result, source='FILE_IMPORT', import_info=info, created_at=meta['created_at'])


def import_package(entry):
    path = Path(entry)
    folder = path if path.is_dir() else path.parent
    if not path.is_dir() and path.name not in ('samples.csv', 'samples.bin', 'metadata.json'):
        raise ValueError('请选择本程序数据包目录或其中的 CSV、BIN、JSON 文件。')
    try:
        return _load(folder)
    except (OSError, ValueError, TypeError, KeyError, AttributeError, OverflowError, csv.Error, RecursionError) as exc:
        raise ValueError('数据包导入失败：' + str(exc)) from exc
