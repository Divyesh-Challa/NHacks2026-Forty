"""Signal filters. Cutoffs come from config.SIGNAL.

All filters are streaming: they keep their state (scipy `zi`) between calls, so feeding a
recording in one go or in 20 ms chunks gives the same output. That's what lets the live source,
the plotter and offline tests share one code path.

- Shared-electrode EOG (A0/A1): each differential channel uses a 4th-order Butterworth low-pass
  at ~10 Hz before the pipeline reconstructs horizontal and vertical movement. Eye movements and
  blinks live below that; 60 Hz pickup does not. Drift is NOT removed here:
  a 0.1 Hz high-pass turns "look left, hold, look back" into a left step followed by a fake right
  overshoot. Detectors instead subtract a slow baseline that freezes during a movement
  (see detectors.Baseline).
- The shared electrode geometry provides common-mode blink information while the channel difference
  suppresses blink artifacts in the vertical movement signal.
"""

import numpy as np
from scipy.signal import butter, sosfilt, sosfilt_zi

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


def eog_filter(x: np.ndarray, fs: float = FS) -> np.ndarray:
    """One-shot EOG low-pass (offline use)."""
    return EogFilter(fs)(x)
