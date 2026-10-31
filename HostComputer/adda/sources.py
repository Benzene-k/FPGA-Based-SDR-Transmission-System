import numpy as np


class DataSource:
    def capabilities(self):
        raise NotImplementedError

    def chunks(self, config, cancel):
        raise NotImplementedError


class LocalTestSource(DataSource):
    def capabilities(self):
        return {'source': 'PC_LOCAL_TEST', 'bits': 8, 'channels': 1,
                'counts': (256, 1024, 4096), 'hardware_output': False}

    def chunks(self, config, cancel):
        config.validate()
        wave = config.wave
        if wave.kind in ('walking', 'external_adc'):
            raise ValueError('Walking 码型仅用于板内数字源。')
        for start in range(0, config.count, 256):
            if cancel.is_set():
                return
            indices = np.arange(start, min(start + 256, config.count))
            if wave.kind == 'sine':
                values = np.rint(wave.offset + wave.amplitude * np.sin(
                    2 * np.pi * indices * (wave.frequency / config.sample_rate)))
            elif wave.kind == 'ramp':
                values = indices % 256
            else:
                values = np.full(len(indices), wave.offset)
            yield values.astype('<u2').tobytes()
