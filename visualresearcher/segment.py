"""Group transcript segments into time windows of a configurable target length.

Whisper emits phrase-level segments; we pack consecutive ones into windows of
min_seconds..max_seconds (e.g. 7-9s) without splitting a phrase. A phrase that
is itself longer than max_seconds becomes its own window.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Window:
    index: int
    start: float
    end: float
    text: str
    concepts: list[str] = field(default_factory=list)
    queries: list[str] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return self.end - self.start

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "start": round(self.start, 2),
            "end": round(self.end, 2),
            "duration": round(self.duration, 2),
            "text": self.text,
            "concepts": self.concepts,
            "queries": self.queries,
        }


def build_windows(segments: list[dict], min_seconds: float, max_seconds: float) -> list[Window]:
    if min_seconds > max_seconds:
        raise ValueError("segmentation.min_seconds must be <= max_seconds")

    windows: list[Window] = []
    current: list[dict] = []

    def flush() -> None:
        if not current:
            return
        windows.append(
            Window(
                index=len(windows) + 1,
                start=current[0]["start"],
                end=current[-1]["end"],
                text=" ".join(s["text"].strip() for s in current if s["text"].strip()),
            )
        )
        current.clear()

    for seg in segments:
        if current:
            span = seg["end"] - current[0]["start"]
            held = current[-1]["end"] - current[0]["start"]
            # Adding this phrase would blow past max: close the window now if
            # we already hold at least min, if stopping short beats
            # overshooting, or if the incoming phrase is long enough to stand
            # alone.
            if span > max_seconds and (
                held >= min_seconds
                or (min_seconds - held) < (span - max_seconds)
                or seg["end"] - seg["start"] >= max_seconds
            ):
                flush()
        current.append(seg)

    flush()

    # Merge a trailing runt window into its predecessor when the result stays
    # within 20% of max — a slightly long final window beats a useless stub.
    if len(windows) >= 2 and windows[-1].duration < min_seconds / 2:
        prev, last = windows[-2], windows[-1]
        if (last.end - prev.start) <= max_seconds * 1.2:
            prev.end = last.end
            prev.text = f"{prev.text} {last.text}".strip()
            windows.pop()

    return windows
