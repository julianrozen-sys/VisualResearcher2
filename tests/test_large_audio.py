import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from visualresearcher import audio  # noqa: E402
from visualresearcher.transcribe import _with_retries, transcribe_in_chunks  # noqa: E402


def make_audio(path: Path, seconds: int) -> None:
    """Tone with a 1s pause every 7s, as small 8 kHz mono WAV."""
    subprocess.run(
        [audio.find_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
         f"sine=frequency=440:sample_rate=8000:duration={seconds}", "-ac", "1", "-af",
         "volume='if(lt(mod(t,7),6),1,0)':eval=frame", str(path)],
        check=True,
    )


def test_plan_cuts_short_file_is_single_chunk():
    assert audio.plan_cuts(100, 600, []) == []
    assert audio.plan_cuts(700, 600, []) == []  # within 25% tolerance


def test_plan_cuts_prefers_pauses_near_target():
    silences = [(590.0, 591.0), (400.0, 401.0), (1195.0, 1196.0)]
    cuts = audio.plan_cuts(1800, 600, silences)
    assert cuts[0] == 590.5
    assert cuts[1] == 1195.5


def test_plan_cuts_without_silence_uses_fixed_interval():
    cuts = audio.plan_cuts(3000, 600, [])
    assert cuts == [600.0, 1200.0, 1800.0, 2400.0]
    assert all(b - a <= 600 * 1.25 + 1e-6 for a, b in zip([0, *cuts], [*cuts, 3000]))


def test_chunks_are_stitched_onto_original_timeline():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        src = tmp / "long.wav"
        make_audio(src, 200)
        calls = []

        def fake(path: Path) -> dict:
            calls.append(path.name)
            dur = audio.probe_duration(path)
            # one segment spanning the whole chunk, plus one in the middle
            return {"text": "hello", "segments": [
                {"start": 0.0, "end": dur, "text": "whole"},
                {"start": dur / 2, "end": dur / 2 + 1, "text": "mid"},
            ]}

        cfg = {"max_direct_mb": 0.01, "chunk_minutes": 1}
        result = transcribe_in_chunks(src, cfg, tmp / "work", fake)
        assert len(calls) >= 3
        wholes = [s for s in result["segments"] if s["text"] == "whole"]
        # first chunk starts at 0, and the chunks tile the file with no gaps or overlaps
        assert wholes[0]["start"] == 0.0
        for a, b in zip(wholes, wholes[1:]):
            assert abs(a["end"] - b["start"]) < 0.3
        assert abs(wholes[-1]["end"] - 200) < 0.5

        # a second run must reuse the cache and not call the transcriber again
        calls.clear()
        again = transcribe_in_chunks(src, cfg, tmp / "work", fake)
        assert calls == []
        assert again["segments"] == result["segments"]


def test_small_file_goes_direct_without_ffmpeg_split():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        src = tmp / "short.wav"
        make_audio(src, 10)
        seen = []

        def fake(path: Path) -> dict:
            seen.append(path)
            return {"text": "x", "segments": [{"start": 0, "end": 1, "text": "x"}]}

        transcribe_in_chunks(src, {"max_direct_mb": 20, "chunk_minutes": 10}, tmp / "w", fake)
        assert seen == [src]
        assert not (tmp / "w").exists()


def test_retries_then_succeeds():
    import visualresearcher.transcribe as t

    t.time.sleep = lambda s: None
    attempts = {"n": 0}

    def flaky(path):
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise RuntimeError("boom")
        return {"text": "ok", "segments": []}

    assert _with_retries(flaky, Path("x.mp3"))["text"] == "ok"
    assert attempts["n"] == 3


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok {name}")
    print("all large-audio tests passed")
