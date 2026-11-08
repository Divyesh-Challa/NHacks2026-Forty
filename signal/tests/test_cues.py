"""Cue-driven recording: the page is told each prompt as the data gets labelled."""

from calibration import load_csv
from tools import record as rec


class FakeCues:
    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.started = False

    def wait_for_start(self) -> None:
        self.started = True

    def send(self, **msg) -> None:
        self.sent.append(msg)


def test_cues_match_the_labelled_data(monkeypatch, tmp_path) -> None:
    for name in ("PROMPT_S", "REST_S", "READY_S"):
        monkeypatch.setattr(rec, name, 0.05)
    cues = FakeCues()
    out = rec.record(rec.SyntheticStream(), reps=1, rest=0.1, out=tmp_path / "s.csv", cues=cues)

    kinds = [m["type"] for m in cues.sent]
    assert cues.started and kinds[:2] == ["ready", "intro"] and kinds[-1] == "done"
    prompts = [m["gesture"] for m in cues.sent if m["type"] == "cue"]
    assert sorted(prompts) == ["blink_double", "look_left", "look_right"]  # synthetic: no vertical
    _, labels = load_csv(out)
    assert {g for g in labels if g != "rest"} == set(prompts)  # what was shown is what was labelled


def test_real_hardware_prompts_include_vertical() -> None:
    p = rec.prompts_for(2, vertical=True)
    assert sorted(set(p)) == ["blink_double", "look_down", "look_left", "look_right", "look_up"]
    assert len(p) == 10
