import hashlib
import math
import zlib
from dataclasses import replace
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from uuid import uuid4

import numpy as np
from typing import Optional


@dataclass(frozen=True)
class WaveConfig:
    kind: str = 'sine'
    frequency: float = 39062.5
    amplitude: int = 32
    offset: int = 128


@dataclass(frozen=True)
class CaptureConfig:
    count: int = 4096
    sample_rate: float = 10000000.0
    wave: WaveConfig = WaveConfig()

    def validate(self):
        if type(self.count) is not int or self.count not in (256, 1024, 4096):
            raise ValueError('点数请选择 256、1024 或 4096。')
        if not math.isfinite(self.sample_rate) or not 1 <= self.sample_rate <= 1e9:
            raise ValueError('配置采样率须为 1～1e9 Sa/s 的有限值。')
        wave = self.wave
        if wave.kind not in ('sine', 'fixed', 'ramp', 'walking', 'external_adc'):
            raise ValueError('不支持的本地波形。')
        if type(wave.offset) is not int or not 0 <= wave.offset <= 255:
            raise ValueError('固定码/偏置须为 0～255 code。')
        if type(wave.amplitude) is not int or not 0 <= wave.amplitude <= 255:
            raise ValueError('数字峰值幅度须为 0～255 code。')
        if wave.kind == 'sine':
            if not math.isfinite(wave.frequency) or not 0 < wave.frequency < self.sample_rate / 2:
                raise ValueError('正弦频率须大于 0 且小于配置采样率的一半。')
            if wave.offset - wave.amplitude < 0 or wave.offset + wave.amplitude > 255:
                raise ValueError('偏置 ± 峰值幅度须在 0～255 code 内；不会自动削顶。')


@dataclass(frozen=True)
class ImportInfo:
    package_path: str
    imported_at: str
    declared_source: str
    source_snapshot_id: str


@dataclass(frozen=True)
class DigitalInfo:
    session: int
    capture_id: int
    crc32: Optional[int]
    verified: bool
    rate_basis: str = 'test_image_nominal_50MHz_not_measured'
    sample_rate: Optional[int] = None


@dataclass(frozen=True)
class Snapshot:
    snapshot_id: str
    task_id: str
    created_at: str
    config: CaptureConfig
    raw: bytes
    status: str
    source: str = 'PC_LOCAL_TEST'
    effective_bits: int = 8
    import_info: Optional[ImportInfo] = None
    digital_info: Optional[DigitalInfo] = None

    @property
    def samples(self):
        return np.frombuffer(self.raw, dtype='<u2')

    @property
    def raw_sha256(self):
        return hashlib.sha256(self.raw).hexdigest()


def make_snapshot(task_id, config, raw, status):
    config.validate()
    raw = bytes(raw)
    if not raw or len(raw) % 2:
        raise ValueError('原始数据为空或 u16 字节未对齐。')
    samples = np.frombuffer(raw, dtype='<u2')
    if len(samples) > config.count or np.any(samples > 255):
        raise ValueError('样本数量或 8 位原始码范围不符。')
    if status not in ('complete', 'partial'):
        raise ValueError('快照状态必须为完整或部分。')
    if status == 'complete' and len(samples) != config.count:
        raise ValueError('未取得期望点数，不能发布完整快照。')
    created = datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='milliseconds')
    return Snapshot(str(uuid4()), task_id, created, config, raw, status)


def make_digital_snapshot(config, result):
    complete = result.state == 'complete'
    external = config.wave.kind == 'external_adc'
    rate = result.sample_rate or 50000000
    if (rate not in (10000000, 25000000, 50000000) or (not external and result.source is not None
            and result.source != {'ramp': 0, 'fixed': 1, 'walking': 2}.get(config.wave.kind))):
        raise ValueError('采样率或冻结来源与配置不一致。')
    if external and (result.source != 3 or result.sample_rate not in (10000000, 25000000)):
        raise ValueError('真实 ADC 来源或采样率未确认。')
    if (result.planned != config.count or config.sample_rate != rate
            or config.wave.kind not in ('ramp', 'fixed', 'walking', 'external_adc')
            or type(result.session) is not int or not 1 <= result.session <= 0xffffffff
            or type(result.capture_id) is not int or not 1 <= result.capture_id <= 0xffffffff
            or result.state not in ('complete', 'cancelled')
            or (complete and (result.verified is not True or result.crc32 != zlib.crc32(result.raw)))):
        raise ValueError('板内数字源身份、点数或整段 CRC32 未通过，不能发布完整快照。')
    snapshot = make_snapshot('digital-{}-{}'.format(result.session, result.capture_id),
                             config, result.raw, 'complete' if complete else 'partial')
    return replace(snapshot, source='FPGA_EXTERNAL_ADC' if external else 'FPGA_INTERNAL_DIGITAL_TEST',
                   digital_info=DigitalInfo(result.session, result.capture_id,
                                            result.crc32 if complete else None, complete,
                                            'firmware_declared_nominal_not_measured' if rate != 50000000 else 'test_image_nominal_50MHz_not_measured',
                                            int(rate) if rate != 50000000 else None))
