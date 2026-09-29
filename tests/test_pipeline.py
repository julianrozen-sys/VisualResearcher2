import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from visualresearcher.concepts import _extract_rules, _normalize  # noqa: E402
from visualresearcher.config import Config  # noqa: E402
from visualresearcher.segment import Window, build_windows  # noqa: E402


def seg(start, end, text="x"):
    return {"start": start, "end": end, "text": text}


def test_windows_respect_bounds():
    segments = [seg(i * 3.0, (i + 1) * 3.0, f"phrase {i}") for i in range(10)]
    windows = build_windows(segments, 7, 9)
    # windows never exceed max by more than the 20% runt-merge tolerance
    assert all(w.duration <= 9.0 * 1.2 for w in windows)
    # all but possibly the last should be >= min
    assert all(w.duration >= 7.0 for w in windows[:-1])
    # full coverage, in order, no overlap
    assert windows[0].start == 0.0 and windows[-1].end == 30.0
    for a, b in zip(windows, windows[1:]):
        assert a.end == b.start


def test_long_phrase_stands_alone():
    segments = [seg(0, 2, "short"), seg(2, 14, "very long phrase"), seg(14, 16, "tail")]
    windows = build_windows(segments, 7, 9)
    assert any(w.text == "very long phrase" for w in windows)


def test_trailing_runt_merges():
    segments = [seg(0, 8, "a"), seg(8, 9.5, "b")]
    windows = build_windows(segments, 7, 9)
    assert len(windows) == 1
    assert windows[0].text == "a b"


def test_query_template_and_aliases():
    config = Config()
    config.raw["theme"]["name"] = "star wars"
    config.raw["theme"]["query_template"] = "{concept} star wars"
    config.raw["theme"]["aliases"] = {"vader": "darth vader"}
    concepts = _normalize(["Vader", "vader", "Death  Star", "Empire's"], config)
    assert concepts == ["darth vader", "death star", "empire"]
    assert config.build_query(concepts[0]) == "darth vader star wars"


def test_rules_extractor_finds_proper_nouns():
    config = Config()
    w = Window(index=1, start=0, end=8, text="Then Darth Vader boarded the Death Star quickly.")
    _extract_rules([w], config)
    lowered = [c.lower() for c in w.concepts]
    assert "darth vader" in lowered
    assert "death star" in lowered


def test_boost_terms_rank_first():
    config = Config()
    config.raw["theme"]["boost_terms"] = ["jedi"]
    w = Window(index=1, start=0, end=8, text="The pilot spoke about ancient jedi traditions.")
    _extract_rules([w], config)
    assert "jedi" in w.concepts[0].lower()


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok {name}")
    print("all tests passed")
