"""Transcription backends. All return the same shape:

{
  "text": "...",
  "segments": [{"start": 0.0, "end": 4.2, "text": "..."}, ...]
}

The OpenAI backend accepts files of any size: anything over the direct-upload
limit is split into chunks (see audio.py), each chunk is transcribed, and the
timestamps are shifted back onto the original timeline. Finished chunks are
cached in the work directory, so an interrupted run resumes instead of
re-paying for audio that was already transcribed.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Callable

from . import audio

DIRECT_EXTENSIONS = {".flac", ".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".ogg", ".wav", ".webm"}
RETRIES = 3


def load_transcript(path: str | Path) -> dict:
    data = json.loads(Path(path).read_text())
    if "segments" not in data:
        raise ValueError(f"{path} has no 'segments' key; expected a VisualResearcher transcript")
    return data


def transcribe(audio_path: str | Path, cfg: dict, work_dir: str | Path | None = None) -> dict:
    audio_path = Path(audio_path)
    if not audio_path.is_file():
        raise ValueError(f"Audio file not found: {audio_path}")
    backend = cfg.get("transcriber", "openai")
    if backend == "openai":
        return _transcribe_openai(audio_path, cfg, Path(work_dir) if work_dir else None)
    if backend == "local":
        return _transcribe_local(audio_path, cfg)
    raise ValueError(f"Unknown transcriber: {backend!r} (expected 'openai' or 'local')")


# --- OpenAI (chunked) ----------------------------------------------------------------

def _transcribe_openai(audio_path: Path, cfg: dict, work_dir: Path | None) -> dict:
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Set it, or use --transcriber local "
            "(pip install faster-whisper), or pass --transcript with an existing transcript."
        )
    from openai import OpenAI

    client = OpenAI()
    language = cfg.get("language") or None

    def chunk_fn(path: Path) -> dict:
        with open(path, "rb") as fh:
            result = client.audio.transcriptions.create(
                model="whisper-1", file=fh, response_format="verbose_json", language=language,
            )
        return {
            "text": result.text,
            "segments": [
                {"start": float(s.start), "end": float(s.end), "text": s.text.strip()}
                for s in (result.segments or [])
            ],
        }

    return transcribe_in_chunks(audio_path, cfg, work_dir, chunk_fn)


def transcribe_in_chunks(
    audio_path: Path,
    cfg: dict,
    work_dir: Path | None,
    chunk_fn: Callable[[Path], dict],
) -> dict:
    """Transcribe a file of any size with chunk_fn, which transcribes one small audio file."""
    max_direct = float(cfg.get("max_direct_mb", 20)) * 1024 * 1024
    chunk_seconds = float(cfg.get("chunk_minutes", 10)) * 60

    if audio_path.stat().st_size <= max_direct and audio_path.suffix.lower() in DIRECT_EXTENSIONS:
        return _with_retries(chunk_fn, audio_path)

    work = (work_dir or audio_path.parent / "_work") / "chunks"
    print(f"      File is {audio_path.stat().st_size / 1e6:.0f} MB; splitting into "
          f"~{chunk_seconds / 60:g} min chunks")
    chunks = audio.split_audio(audio_path, work, chunk_seconds)
    print(f"      {len(chunks)} chunks ready")

    segments: list[dict] = []
    texts: list[str] = []
    for i, (offset, chunk_path) in enumerate(chunks, start=1):
        cache = chunk_path.with_suffix(".json")
        if cache.exists():
            result = json.loads(cache.read_text())
            note = "cached"
        else:
            result = _with_retries(chunk_fn, chunk_path)
            cache.write_text(json.dumps(result))
            note = "done"
        print(f"      chunk {i}/{len(chunks)} {note} (starts at {offset / 60:.1f} min)")
        texts.append(result["text"].strip())
        for seg in result["segments"]:
            segments.append({
                "start": round(seg["start"] + offset, 3),
                "end": round(seg["end"] + offset, 3),
                "text": seg["text"],
            })
    return {"text": " ".join(t for t in texts if t), "segments": segments}


def _with_retries(fn: Callable[[Path], dict], path: Path) -> dict:
    for attempt in range(1, RETRIES + 1):
        try:
            return fn(path)
        except Exception as exc:
            if attempt == RETRIES:
                raise RuntimeError(f"Transcription failed for {path.name} after {RETRIES} tries: {exc}") from exc
            wait = 2 ** attempt
            print(f"      transcription error ({exc}); retrying in {wait}s")
            time.sleep(wait)
    raise AssertionError("unreachable")


# --- Local -----------------------------------------------------------------------------

def _transcribe_local(audio_path: Path, cfg: dict) -> dict:
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError(
            "Local transcription requires faster-whisper: pip install faster-whisper"
        ) from exc

    # faster-whisper streams audio itself, so file size is not a concern here.
    model = WhisperModel(cfg.get("local_model", "base"), compute_type="auto")
    raw_segments, _info = model.transcribe(str(audio_path), language=cfg.get("language") or None)
    segments = [
        {"start": float(s.start), "end": float(s.end), "text": s.text.strip()}
        for s in raw_segments
    ]
    return {"text": " ".join(s["text"] for s in segments), "segments": segments}
