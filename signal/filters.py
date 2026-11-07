"""Signal filters. Owner: Role B. Cutoffs come from config.SIGNAL.

TODO:
  - eog_filter: low-pass ~10 Hz + drift handling (high-pass ~0.1 Hz or derivative)
  - emg_envelope: bandpass 20-150 Hz, 60 Hz notch, RMS envelope
Prefer scipy.signal sosfilt with persistent zi so filters work sample-by-sample/chunked.
"""

import numpy as np


def eog_filter(x: np.ndarray, fs: float) -> np.ndarray:
    raise NotImplementedError


def emg_envelope(x: np.ndarray, fs: float, window_ms: float = 100) -> np.ndarray:
    raise NotImplementedError
