"""Transcription backends. All return the same shape:

{
  "text": "...",
  "segments": [{"start": 0.0, "end": 4.2, "text": "..."}, ...]
}
"""

from __future__ import annotations

import json
import os
from pathlib import Path


def load_transcript(path: str | Path) -> dict:
    data = json.loads(Path(path).read_text())
    if "segments" not in data:
        raise ValueError(f"{path} has no 'segments' key; expected a VisualResearcher transcript")
    return data


def transcribe(audio_path: str | Path, cfg: dict) -> dict:
    backend = cfg.get("transcriber", "openai")
    if backend == "openai":
        return _transcribe_openai(audio_path, cfg)
    if backend == "local":
        return _transcribe_local(audio_path, cfg)
    raise ValueError(f"Unknown transcriber: {backend!r} (expected 'openai' or 'local')")


def _transcribe_openai(audio_path: str | Path, cfg: dict) -> dict:
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Set it, or use --transcriber local "
            "(pip install faster-whisper), or pass --transcript with an existing transcript."
        )
    from openai import OpenAI

    client = OpenAI()
    with open(audio_path, "rb") as fh:
        result = client.audio.transcriptions.create(
            model="whisper-1",
            file=fh,
            response_format="verbose_json",
            language=cfg.get("language") or None,
        )
    segments = [
        {"start": float(s.start), "end": float(s.end), "text": s.text.strip()}
        for s in (result.segments or [])
    ]
    return {"text": result.text, "segments": segments}


def _transcribe_local(audio_path: str | Path, cfg: dict) -> dict:
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError(
            "Local transcription requires faster-whisper: pip install faster-whisper"
        ) from exc

    model = WhisperModel(cfg.get("local_model", "base"), compute_type="auto")
    raw_segments, _info = model.transcribe(str(audio_path), language=cfg.get("language") or None)
    segments = [
        {"start": float(s.start), "end": float(s.end), "text": s.text.strip()}
        for s in raw_segments
    ]
    return {"text": " ".join(s["text"] for s in segments), "segments": segments}
