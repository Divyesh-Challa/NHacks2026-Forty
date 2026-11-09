"""Calibration: thresholds adapt to the person, accuracy numbers, polarity, live source seeding."""

import numpy as np

from calibration import calibrate, segments, synthetic_session
from sources.pipeline import PipelineSource
from sources.synthetic import SyntheticEXG


class Rows:
    def __init__(self, rows):
        self.rows = rows

    def read(self):
        r, self.rows = self.rows, self.rows[:0]
        return r


def test_segments() -> None:
    t = np.arange(6)
    assert segments(t, ["rest", "rest", "look_left", "look_left", "rest", "rest"]) == [
        ("rest", 0, 1), ("look_left", 2, 3), ("rest", 4, 5)
    ]


def test_synthetic_calibration_is_accurate_with_no_false_triggers() -> None:
    result = calibrate(*synthetic_session(reps=6, seed=1))
    for sig in ("eog_h", "blink"):
        r = result["signals"][sig]
        assert r["accuracy"] >= 0.9 and r["false_trigger_rate"] <= 0.05, (sig, r)
    assert result["signals"]["eog_h"]["attempts"] == 12  # left + right
    assert result["settings"]["eog_invert"] is False


def test_thresholds_follow_the_persons_amplitude() -> None:
    strong = calibrate(*synthetic_session(reps=4, seed=2))["settings"]
    weak = calibrate(*synthetic_session(reps=4, seed=2, gain={"eog_h": 0.5}))["settings"]
    assert weak["eog_threshold"] < 0.7 * strong["eog_threshold"]
    assert weak["eog_floor"] < weak["eog_threshold"]


def test_inverted_electrodes_are_detected() -> None:
    rows, labels = synthetic_session(reps=4, seed=3)
    flipped = rows.copy()
    flipped[:, 1] = 1024 - flipped[:, 1]  # electrodes swapped: left reads positive
    result = calibrate(flipped, labels)
    assert result["settings"]["eog_invert"] is True
    assert result["signals"]["eog_h"]["accuracy"] >= 0.9


def test_live_source_uses_calibration_and_near_misses_lower_reliability() -> None:
    cal = calibrate(*synthetic_session(reps=4, seed=4))
    exg = SyntheticEXG(seed=5)
    exg.degrade("eye", 0.3)
    for i in range(8):
        exg.trigger("look_left" if i % 2 else "look_right", delay_s=1.0 + 2.0 * i)
    src = PipelineSource(Rows(exg.chunk(19 * 500)), calibration=cal)
    assert src.reliability()["signals"]["eog_h"] >= 0.9  # seeded from calibration
    assert src.handle(src.stream.read()) == []  # weak looks aren't detected...
    assert src.reliability()["signals"]["eog_h"] < 0.6  # ...and the near-misses count against it


class SyntheticRows:
    """A synthetic stream that hands out `seconds` of samples per read (PipelineSource drives exg)."""

    def __init__(self, seconds: float, seed: int) -> None:
        self.exg = SyntheticEXG(seed=seed)
        self.n = int(seconds * 500)

    def read(self):
        return self.exg.chunk(self.n)


def test_eye_degrade_lowers_both_eye_signals_through_the_real_detectors(monkeypatch) -> None:
    """run.py --detectors real: an "eye" degrade must take eog_v down with eog_h (the wheel needs both)."""
    import calibration

    monkeypatch.setattr(calibration, "DETECTOR_OVERRIDES", {})  # pins are for the rig, not synthetic amplitudes
    src =PipelineSource(SyntheticRows(2.0, seed=6), calibration=calibrate(*synthetic_session(reps=4, seed=4)))
    first = src.reliability()["signals"]
    assert set(first) == {"eog_h", "eog_v", "blink"}
    src.degrade("eye", 0.3)
    for g in ["look_left", "look_up", "look_right", "look_down", "blink_double"] * 4:
        src.trigger(g)
        src.handle(src.stream.read())
    r = src.reliability()["signals"]
    assert r["eog_h"] < 0.6 and r["eog_v"] < 0.6
    assert r["blink"] >= 0.75
    src.degrade("eye", 1.0)
    assert not src.pipeline.vert.misses


def test_pinned_overrides_survive_calibration(monkeypatch) -> None:
    import calibration

    monkeypatch.setattr(calibration, "DETECTOR_OVERRIDES", {"vert_threshold": 28.0, "vert_rearm_ms": 0})
    s = calibrate(*synthetic_session(reps=4, seed=6))["settings"]
    assert s["vert_threshold"] == 28.0 and s["vert_rearm_ms"] == 0


def test_rail_warning_flags_a_saturating_channel() -> None:
    from calibration import rail_warnings

    rows, _ = synthetic_session(reps=2, seed=7)
    assert rail_warnings(rows) == []
    bad = rows.copy()
    bad[: len(bad) // 10, 1] = 1020  # A0 pinned at the top rail for 10% of the run
    assert len(rail_warnings(bad)) == 1 and "A0" in rail_warnings(bad)[0]


def test_first_movement_ignores_larger_opposite_return() -> None:
    from calibration import first_movement

    d = np.zeros(1000)
    d[100:200] = -60
    d[650:750] = 180
    assert first_movement(d, noise=2, fs=500) == -60


def test_calibration_scores_wrong_extras_as_errors(monkeypatch) -> None:
    import calibration
    from detectors import Detection

    class FakePipeline:
        def __init__(self, *args):
            pass

        def process(self, rows):
            return [Detection('eog_h', 'look_left', 1, 100), Detection('eog_v', 'look_up', 1, 120)] if rows[0, 0] == 0 else []

    monkeypatch.setattr(calibration, 'Pipeline', FakePipeline)
    rows = np.column_stack([np.arange(500) * 2000, np.full((500, 3), 512)])
    r = calibration.evaluate(rows, ['look_left'] * 500, {})['eog_h']
    assert r['accuracy'] == 0 and r['hits'] == 1 and r['extra_commands'] == 1


def test_direction_thresholds_are_independent(monkeypatch) -> None:
    import calibration

    monkeypatch.setattr(calibration, 'DETECTOR_OVERRIDES', {})
    m = {'eog_invert': False, 'vert_invert': False,
         'amplitude': {'eog_h': 100, 'eog_v': 80, 'blink': 300},
         'noise': {'eog_h': 5, 'eog_v': 5, 'blink': 5},
         'direction_amplitudes': {'look_up': 100, 'look_down': 40}}
    s = calibration.thresholds(m)
    assert s['look_up_threshold'] == 50 and s['look_down_threshold'] == 20


def test_ambiguous_polarity_rejects_candidate(monkeypatch) -> None:
    import calibration

    rows, labels = synthetic_session(reps=4, seed=8)
    original = calibration.measure

    def ambiguous(*args):
        m = original(*args)
        m['polarity_agreement']['eog_h'] = .5
        return m

    monkeypatch.setattr(calibration, 'measure', ambiguous)
    result = calibrate(rows, labels)
    assert not result['valid']
    assert any('polarity' in w for w in result['warnings'])


def test_rejected_candidate_preserves_active_calibration(tmp_path, monkeypatch) -> None:
    import json
    import calibration

    monkeypatch.setattr(calibration, 'HERE', tmp_path)
    monkeypatch.setattr(calibration, 'CAL_PATH', tmp_path / 'calibration.json')
    active = '{"existing": true}'
    (tmp_path / 'calibration.json').write_text(active)
    monkeypatch.setattr(calibration, 'synthetic_session', lambda *args: (None, None))
    monkeypatch.setattr(calibration, 'calibrate', lambda *args: {'valid': False, 'warnings': ['bad contact']})
    monkeypatch.setattr(calibration, 'report', lambda *args: 'rejected')
    monkeypatch.setattr('sys.argv', ['calibration.py', '--no-post'])
    calibration.main()
    assert (tmp_path / 'calibration.json').read_text() == active
    assert json.loads(next((tmp_path / 'recordings').glob('*.json')).read_text())['valid'] is False


def test_accepted_candidate_backs_up_previous_calibration(tmp_path, monkeypatch) -> None:
    import json
    import calibration

    monkeypatch.setattr(calibration, 'HERE', tmp_path)
    monkeypatch.setattr(calibration, 'CAL_PATH', tmp_path / 'calibration.json')
    active = '{"existing": true}'
    (tmp_path / 'calibration.json').write_text(active)
    candidate = {'valid': True, 'warnings': []}
    monkeypatch.setattr(calibration, 'synthetic_session', lambda *args: (None, None))
    monkeypatch.setattr(calibration, 'calibrate', lambda *args: candidate)
    monkeypatch.setattr(calibration, 'report', lambda *args: 'accepted')
    monkeypatch.setattr('sys.argv', ['calibration.py', '--no-post'])
    calibration.main()
    assert json.loads((tmp_path / 'calibration.json').read_text()) == candidate
    assert (tmp_path / 'calibration.prev.json').read_text() == active


def test_sparse_rest_spikes_do_not_set_background_threshold() -> None:
    from calibration import rest_noise

    rng = np.random.default_rng(23)
    quiet = 512 + rng.normal(0, 5, 500)
    blinking = quiet.copy()
    blinking[100:125] += 350
    blinking[125:150] -= 250
    assert 4 < rest_noise(quiet) < 6
    assert rest_noise(blinking) < 7
    assert rest_noise(512 + rng.normal(0, 40, 500)) > 30
