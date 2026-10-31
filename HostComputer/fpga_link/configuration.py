from dataclasses import dataclass
import struct

@dataclass(frozen=True)
class CommConfig:
    frame_symbols: int = 30
    sync_symbols: int = 13
    random_seed: int = 20260919

    def validate(self):
        values = (self.frame_symbols, self.sync_symbols, self.random_seed)
        if any(type(value) is not int for value in values):
            raise ValueError('Configuration values must be integers')
        if not 2 <= self.frame_symbols <= 4096:
            raise ValueError('Frame symbols must be 2..4096')
        if not 1 <= self.sync_symbols <= 1024 or self.sync_symbols >= self.frame_symbols:
            raise ValueError('Sync symbols must be 1..1024 and less than frame symbols')
        if not 0 <= self.random_seed <= 2147483647:
            raise ValueError('Random seed must be 0..2147483647')

    def encode(self):
        self.validate()
        return struct.pack('>HHI', self.frame_symbols, self.sync_symbols, self.random_seed)

    @classmethod
    def decode(cls, payload):
        if len(payload) != 8:
            raise ValueError('Configuration reply must contain 8 bytes')
        result = cls(*struct.unpack('>HHI', payload))
        result.validate()
        return result
