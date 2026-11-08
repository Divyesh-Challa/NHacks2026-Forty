"""Filters: streaming equals one-shot, EOG low-pass keeps movements and drops muscle noise/mains."""

import numpy as np

from filters import FS, EogFilter, eog_filter

t = np.arange(4 * FS) / FS


def test_streaming_matches_one_shot() -> None:
    x = np.random.default_rng(0).normal(512, 20, size=t.size)
    f = EogFilter()
    chunked = np.concatenate([f(x[i : i + 37]) for i in range(0, x.size, 37)])
    assert np.allclose(chunked, eog_filter(x))


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
