"""Signal filters. Cutoffs come from config.SIGNAL.

All filters are streaming: they keep their state (scipy `zi`) between calls, so feeding a
recording in one go or in 20 ms chunks gives the same output. That's what lets the live source,
the plotter and offline tests share one code path.

- EOG (A0 horizontal, A1 vertical/blink): 4th-order Butterworth low-pass at ~10 Hz. Eye movements
  and blinks live below that; jaw EMG crosstalk and 60 Hz pickup don't. Drift is NOT removed here:
  a 0.1 Hz high-pass turns "look left, hold, look back" into a left step followed by a fake right
  overshoot. Detectors instead subtract a slow baseline that freezes during a movement
  (see detectors.Baseline).
- EMG (A2 jaw): 4th-order Butterworth bandpass 20–150 Hz (Nyquist at 500 Hz is 250), a 60 Hz notch
  for mains, then an RMS envelope (EMA of x², ~50 ms) — clench = envelope goes up.
"""

import numpy as np
from scipy.signal import butter, iirnotch, lfilter, lfilter_zi, sosfilt, sosfilt_zi, tf2sos

from config import SIGNAL

FS = SIGNAL["sample_rate_hz"]


class Streaming:
    """An SOS filter that keeps its state across calls."""

    def __init__(self, sos: np.ndarray) -> None:
        self.sos = sos
        self.zi: np.ndarray | None = None

    def __call__(self, x: np.ndarray) -> np.ndarray:
        x = np.asarray(x, dtype=float)
        if x.size == 0:
            return x
        if self.zi is None:  # start at steady state for the first sample (no start-up transient)
            self.zi = sosfilt_zi(self.sos) * x[0]
        y, self.zi = sosfilt(self.sos, x, zi=self.zi)
        return y


class EogFilter(Streaming):
    def __init__(self, fs: float = FS, cutoff_hz: float = SIGNAL["eog_lowpass_hz"]) -> None:
        super().__init__(butter(4, cutoff_hz, btype="low", fs=fs, output="sos"))


class EmgEnvelope:
    """Bandpass + notch + RMS envelope, in ADC counts."""

    def __init__(
        self,
        fs: float = FS,
        band_hz: tuple[float, float] = tuple(SIGNAL["emg_band_hz"]),
        notch_hz: float = SIGNAL["notch_hz"],
        window_ms: float = SIGNAL["emg_rms_ms"],
    ) -> None:
        hi = min(band_hz[1], 0.45 * fs)
        bp = butter(4, [band_hz[0], hi], btype="band", fs=fs, output="sos")
        notch = tf2sos(*iirnotch(notch_hz, Q=30, fs=fs))
        self.band = Streaming(np.vstack([bp, notch]))
        # RMS as a one-pole low-pass of x²: cheaper than a sliding window and streams trivially.
        a = 1.0 - np.exp(-1.0 / (fs * window_ms / 1000))
        self._b, self._a = [a], [1.0, a - 1.0]
        self._zi: np.ndarray | None = None

    def __call__(self, x: np.ndarray) -> np.ndarray:
        y = self.band(x)
        if y.size == 0:
            return y
        sq = y * y
        if self._zi is None:
            self._zi = lfilter_zi(self._b, self._a) * sq[0]
        ms, self._zi = lfilter(self._b, self._a, sq, zi=self._zi)
        return np.sqrt(np.maximum(ms, 0.0))


def eog_filter(x: np.ndarray, fs: float = FS) -> np.ndarray:
    """One-shot EOG low-pass (offline use)."""
    return EogFilter(fs)(x)


def emg_envelope(x: np.ndarray, fs: float = FS, window_ms: float = SIGNAL["emg_rms_ms"]) -> np.ndarray:
    """One-shot EMG envelope (offline use)."""
    return EmgEnvelope(fs, window_ms=window_ms)(x)
