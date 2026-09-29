"""End-to-end pipeline: audio/transcript -> windows -> concepts -> queries -> images."""

from __future__ import annotations

import json
from pathlib import Path

from .concepts import extract_concepts
from .config import Config
from .download import download_images, slugify
from .search import search_images
from .segment import build_windows
from .transcribe import load_transcript, transcribe


def run(
    audio_path: str | None,
    transcript_path: str | None,
    config: Config,
    out_dir: str | Path,
    dry_run: bool = False,
) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    # 1. Transcript
    if transcript_path:
        print(f"[1/4] Loading transcript from {transcript_path}")
        transcript = load_transcript(transcript_path)
    else:
        print(f"[1/4] Transcribing {audio_path} "
              f"({config.transcription_cfg.get('transcriber')})")
        transcript = transcribe(audio_path, config.transcription_cfg)
        (out / "transcript.json").write_text(json.dumps(transcript, indent=2))

    # 2. Windows
    windows = build_windows(transcript["segments"], config.min_seconds, config.max_seconds)
    print(f"[2/4] Built {len(windows)} segments of "
          f"{config.min_seconds:g}-{config.max_seconds:g}s")

    # 3. Concepts + queries
    print("[3/4] Extracting concepts and building queries")
    extract_concepts(windows, config)
    for w in windows:
        print(f"  #{w.index:03d} [{w.start:6.1f}-{w.end:6.1f}] {', '.join(w.queries) or '(none)'}")

    # 4. Search + download
    manifest = {
        "theme": config.theme_name,
        "config": config.raw,
        "segments": [],
    }
    seg_root = out / "segments"
    total_images = 0

    for w in windows:
        record = w.to_dict()
        record["images"] = []
        if not dry_run and w.queries:
            results: list[dict] = []
            for concept, query in zip(w.concepts, w.queries):
                try:
                    results.extend(search_images(query, concept, config))
                except Exception as exc:
                    print(f"  ! search failed for {query!r}: {exc}")
            if config.download_cfg.get("enabled", True) and results:
                seg_dir = seg_root / (
                    f"{w.index:03d}_{w.start:.1f}-{w.end:.1f}_"
                    f"{slugify(w.concepts[0]) if w.concepts else 'none'}"
                )
                record["images"] = download_images(results, seg_dir, config.download_cfg)
                record["dir"] = str(seg_dir.relative_to(out))
                (seg_dir / "segment.json").write_text(json.dumps(record, indent=2))
                total_images += len(record["images"])
                print(f"  #{w.index:03d} downloaded {len(record['images'])} images")
            else:
                record["images"] = results
        manifest["segments"].append(record)

    manifest_path = out / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(f"[4/4] Done. {len(windows)} segments, {total_images} images -> {manifest_path}")
    return manifest
