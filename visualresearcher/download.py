"""Download and validate images into per-segment folders."""

from __future__ import annotations

import re
from pathlib import Path

import requests

EXT_BY_TYPE = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
}


def slugify(text: str, max_len: int = 40) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:max_len] or "img"


def download_images(results: list[dict], dest: Path, cfg: dict) -> list[dict]:
    """Download search results into dest. Returns records for the manifest."""
    dest.mkdir(parents=True, exist_ok=True)
    timeout = cfg.get("timeout_seconds", 15)
    min_bytes = cfg.get("min_bytes", 15000)
    max_images = cfg.get("max_images_per_segment", 6)

    saved: list[dict] = []
    for result in results:
        if len(saved) >= max_images:
            break
        url = result["url"]
        try:
            resp = requests.get(url, headers=HEADERS, timeout=timeout, stream=True)
            resp.raise_for_status()
            content_type = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            ext = EXT_BY_TYPE.get(content_type)
            if ext is None:
                # Some hosts serve images with wrong/missing type; trust URL extension.
                url_ext = Path(url.split("?")[0]).suffix.lower()
                if url_ext in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
                    ext = ".jpg" if url_ext == ".jpeg" else url_ext
                else:
                    continue
            data = resp.content
            if len(data) < min_bytes:
                continue
            filename = f"{len(saved) + 1:02d}_{slugify(result['concept'])}{ext}"
            (dest / filename).write_bytes(data)
            saved.append(
                {
                    "file": filename,
                    "url": url,
                    "source": result.get("source", ""),
                    "title": result.get("title", ""),
                    "concept": result["concept"],
                    "query": result["query"],
                }
            )
        except requests.RequestException:
            continue
    return saved
