

def statistics(snapshot):
    codes = snapshot.samples
    return dict(count=len(codes), minimum=int(codes.min()), maximum=int(codes.max()),
                mean=float(codes.mean()), std_population=float(codes.std(ddof=0)))


def spectrum(snapshot, window='hann', remove_dc=True):
    import numpy as np
    samples = snapshot.samples.astype(float)
    count = len(samples)
    if count < 2:
        raise ValueError('频谱至少需要 2 个有效样本。')
    if window not in ('rectangular', 'hann'):
        raise ValueError('未知窗函数。')
    if remove_dc:
        samples -= samples.mean()
    weights = (0.5 - 0.5 * np.cos(2 * np.pi * np.arange(count) / count)
               if window == 'hann' else np.ones(count))
    amplitude = np.abs(np.fft.rfft(samples * weights)) / weights.sum()
    amplitude[1:-1 if count % 2 == 0 else None] *= 2
    frequency = np.fft.rfftfreq(count, 1.0 / snapshot.config.sample_rate)
    peak = int(np.argmax(amplitude))
    no_signal = float(amplitude[peak]) < 1e-10
    return dict(frequency=frequency, amplitude=amplitude,
                peak_frequency=None if no_signal else float(frequency[peak]),
                peak_amplitude=0.0 if no_signal else float(amplitude[peak]),
                bin_width=snapshot.config.sample_rate / count,
                window=window, remove_dc=bool(remove_dc))
