from reliability import ReliabilityTracker, score


def tracker() -> ReliabilityTracker:
    return ReliabilityTracker(attempt_window=8, rest_window=20, default_accuracy=0.9, default_false_trigger_rate=0.05)


def test_formula() -> None:
    assert score(0.9, 0.1) == 0.9 * 0.9
    assert score(1.5, -1) == 1.0  # clamped


def test_seed_sets_starting_reliability() -> None:
    t = tracker()
    t.seed("jaw", accuracy=0.75, false_trigger_rate=0.1)
    assert t.accuracy("jaw") == 6 / 8
    assert t.false_trigger_rate("jaw") == 2 / 20
    assert abs(t.score("jaw") - 0.75 * 0.9) < 1e-9


def test_unseeded_signal_uses_defaults() -> None:
    t = tracker()
    assert abs(t.score("eog_h") - round(0.9 * 8) / 8 * (1 - 1 / 20)) < 1e-9


def test_misses_roll_the_seed_out() -> None:
    t = tracker()
    t.seed("eog_h", 1.0, 0.0)
    for _ in range(4):
        t.record_attempt("eog_h", False)
    assert t.accuracy("eog_h") == 0.5
    for _ in range(4):
        t.record_attempt("eog_h", False)
    assert t.score("eog_h") == 0.0


def test_false_triggers_lower_reliability() -> None:
    t = tracker()
    t.seed("blink", 1.0, 0.0)
    for _ in range(5):
        t.record_rest("blink", True)
    assert t.false_trigger_rate("blink") == 5 / 20
    assert t.score("blink") == 0.75


def test_usage_error_counts_as_a_miss() -> None:
    t = tracker()
    t.seed("jaw", 1.0, 0.0)
    t.record_error("jaw")
    assert t.accuracy("jaw") == 7 / 8


def test_snapshot_is_rounded_and_selectable() -> None:
    t = tracker()
    t.seed("jaw", 0.5, 0.0)
    assert t.snapshot(["jaw"]) == {"jaw": 0.5}
