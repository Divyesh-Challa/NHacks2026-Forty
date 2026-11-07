"""Filters: streaming equals one-shot, EOG low-pass keeps movements and drops EMG/mains, EMG envelope."""

import numpy as np

from filters import FS, EmgEnvelope, EogFilter, emg_envelope, eog_filter

t = np.arange(4 * FS) / FS


def test_streaming_matches_one_shot() -> None:
    x = np.random.default_rng(0).normal(512, 20, size=t.size)
    f, e = EogFilter(), EmgEnvelope()
    chunked = np.concatenate([f(x[i : i + 37]) for i in range(0, x.size, 37)])
    env = np.concatenate([e(x[i : i + 37]) for i in range(0, x.size, 37)])
    assert np.allclose(chunked, eog_filter(x))
    assert np.allclose(env, emg_envelope(x))


def test_no_startup_transient_at_adc_midpoint() -> None:
    y = eog_filter(np.full(FS, 512.0))
    assert np.allclose(y, 512.0)


def test_eog_lowpass_keeps_slow_movement_and_removes_60hz_and_emg() -> None:
    slow = 100 * np.sin(2 * np.pi * 1.0 * t)
    mains = 30 * np.sin(2 * np.pi * 60.0 * t)
    emg = np.random.default_rng(1).normal(0, 30, size=t.size)
    kept = eog_filter(512 + slow)[FS:] - 512
    leak = eog_filter(512 + slow + mains + emg)[FS:] - 512 - kept  # filters are linear
    assert kept.max() > 95  # 1 Hz movement passes at full size
    assert np.std(leak) < 8  # from 36 counts rms; white noise in the 0-10 Hz band (~6) is all that is left


def test_emg_envelope_rises_with_burst_and_ignores_mains() -> None:
    rng = np.random.default_rng(2)
    x = 512 + 20 * np.sin(2 * np.pi * 60.0 * t) + 2 * np.sin(2 * np.pi * 0.3 * t) * 50
    x[2 * FS : 3 * FS] += rng.normal(0, 60, size=FS)
    env = emg_envelope(x)
    rest, burst = env[FS : 2 * FS].max(), np.median(env[2 * FS + 50 : 3 * FS])
    assert rest < 5 and burst > 30
