"""Audio preparation for files too large for a single transcription request.

Any audio or video file (of any size) is decoded by ffmpeg, downmixed to small
mono speech-quality audio, and cut into chunks at natural pauses so words are
not sliced in half. Chunks are written to disk one at a time by ffmpeg, so
memory use stays flat no matter how large the input is.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

# 32 kbps mono mp3 is ~0.24 MB/min: a 10-minute chunk is ~2.4 MB, far below the 25 MB API cap.
CHUNK_BITRATE = "32k"
CHUNK_SAMPLE_RATE = "16000"

SILENCE_NOISE = "-35dB"
SILENCE_MIN_SECONDS = 0.35
# How far either side of the ideal cut point we will look for a pause.
CUT_SEARCH_WINDOW = 45.0


def find_ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError as exc:
        raise RuntimeError(
            "ffmpeg is required to split large audio. Install it with "
            "`pip install imageio-ffmpeg` (bundles ffmpeg) or from ffmpeg.org."
        ) from exc


def _run(args: list[str]) -> str:
    """Run ffmpeg and return stderr (where it prints info). ffmpeg -i with no output exits 1."""
    proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                          errors="replace")
    return proc.stderr


def probe_duration(path: str | Path) -> float:
    err = _run([find_ffmpeg(), "-hide_banner", "-i", str(path)])
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", err)
    if not match:
        raise RuntimeError(f"Could not read audio duration from {path}. Is it a valid audio/video file?")
    h, m, s = match.groups()
    return int(h) * 3600 + int(m) * 60 + float(s)


def detect_silences(path: str | Path) -> list[tuple[float, float]]:
    """Return (start, end) of every pause in the audio."""
    err = _run([
        find_ffmpeg(), "-hide_banner", "-nostats", "-i", str(path), "-vn", "-ac", "1",
        "-ar", CHUNK_SAMPLE_RATE, "-af",
        f"silencedetect=noise={SILENCE_NOISE}:d={SILENCE_MIN_SECONDS}", "-f", "null", "-",
    ])
    starts = [float(x) for x in re.findall(r"silence_start:\s*(-?\d+(?:\.\d+)?)", err)]
    ends = [float(x) for x in re.findall(r"silence_end:\s*(-?\d+(?:\.\d+)?)", err)]
    # A trailing silence has a start with no end; it cannot be a cut point we need anyway.
    return [(max(s, 0.0), e) for s, e in zip(starts, ends)]


def plan_cuts(duration: float, chunk_seconds: float,
              silences: list[tuple[float, float]]) -> list[float]:
    """Choose cut times so chunks are about chunk_seconds long, cutting mid-pause where possible.

    Returns the interior cut points (excluding 0 and duration), ascending.
    """
    if duration <= chunk_seconds * 1.25:
        return []
    cuts: list[float] = []
    last = 0.0
    while duration - last > chunk_seconds * 1.25:
        target = last + chunk_seconds
        best = None
        best_dist = CUT_SEARCH_WINDOW
        for start, end in silences:
            mid = (start + end) / 2
            if mid <= last + chunk_seconds * 0.4 or mid >= duration:
                continue
            dist = abs(mid - target)
            if dist < best_dist:
                best, best_dist = mid, dist
        cut = best if best is not None else target
        cuts.append(round(cut, 3))
        last = cut
    return cuts


def extract_chunk(path: str | Path, start: float, end: float | None, dest: Path) -> None:
    """Write [start, end) of the input to dest as small mono mp3 (end=None means to the end)."""
    args = [find_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y",
            "-ss", f"{start:.3f}", "-i", str(path)]
    if end is not None:
        args += ["-t", f"{end - start:.3f}"]
    # Write to a temp name and rename, so an interrupted run never leaves a truncated chunk
    # that a resumed run would mistake for a finished one.
    tmp = dest.with_name(dest.stem + ".part.mp3")
    args += ["-vn", "-ac", "1", "-ar", CHUNK_SAMPLE_RATE, "-b:a", CHUNK_BITRATE, str(tmp)]
    err = _run(args)
    if not tmp.exists() or tmp.stat().st_size == 0:
        raise RuntimeError(f"ffmpeg failed to extract audio chunk at {start:.1f}s: {err.strip()[-300:]}")
    tmp.replace(dest)


def split_audio(path: str | Path, work_dir: Path, chunk_seconds: float) -> list[tuple[float, Path]]:
    """Split into chunks in work_dir. Returns [(start_offset_seconds, chunk_path), ...]."""
    work_dir.mkdir(parents=True, exist_ok=True)
    duration = probe_duration(path)
    silences = detect_silences(path) if duration > chunk_seconds * 1.25 else []
    cuts = plan_cuts(duration, chunk_seconds, silences)
    bounds = [0.0, *cuts, None]
    chunks: list[tuple[float, Path]] = []
    for i, (start, end) in enumerate(zip(bounds, bounds[1:]), start=1):
        dest = work_dir / f"chunk_{i:04d}.mp3"
        if not (dest.exists() and dest.stat().st_size > 0):  # reuse on resume
            extract_chunk(path, start, end, dest)
        chunks.append((start, dest))
    return chunks
