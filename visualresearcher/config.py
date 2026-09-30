"""Project configuration: everything customizable lives here, loaded from YAML."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULTS: dict = {
    "theme": {
        "name": "",
        "query_template": "{concept} {theme}",
        "aliases": {},
        "boost_terms": [],
        "exclude_terms": [],
    },
    "segmentation": {
        "min_seconds": 7.0,
        "max_seconds": 9.0,
    },
    "concepts": {
        "extractor": "auto",  # auto | llm | rules
        "max_per_segment": 3,
        "llm_model": "claude-haiku-4-5-20251001",
    },
    "search": {
        "provider": "duckduckgo",  # duckduckgo | google
        "images_per_concept": 3,
        "safe_search": True,
    },
    "download": {
        "enabled": True,
        "timeout_seconds": 15,
        "min_bytes": 15000,
        "max_images_per_segment": 6,
    },
    "transcription": {
        "transcriber": "openai",  # openai | local
        "language": None,
        "local_model": "base",
        "max_direct_mb": 20,  # larger files are split into chunks (OpenAI API caps uploads at 25 MB)
        "chunk_minutes": 10,
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


@dataclass
class Config:
    raw: dict = field(default_factory=lambda: copy.deepcopy(DEFAULTS))

    @classmethod
    def load(cls, path: str | Path | None) -> "Config":
        if path is None:
            return cls()
        data = yaml.safe_load(Path(path).read_text()) or {}
        return cls(raw=_deep_merge(DEFAULTS, data))

    # --- convenience accessors -------------------------------------------------
    @property
    def theme_name(self) -> str:
        return str(self.raw["theme"].get("name") or "").strip()

    @property
    def query_template(self) -> str:
        return self.raw["theme"].get("query_template") or "{concept} {theme}"

    @property
    def aliases(self) -> dict[str, str]:
        return {str(k).lower(): str(v) for k, v in (self.raw["theme"].get("aliases") or {}).items()}

    @property
    def boost_terms(self) -> list[str]:
        return [str(t).lower() for t in self.raw["theme"].get("boost_terms") or []]

    @property
    def exclude_terms(self) -> list[str]:
        return [str(t).lower() for t in self.raw["theme"].get("exclude_terms") or []]

    @property
    def min_seconds(self) -> float:
        return float(self.raw["segmentation"]["min_seconds"])

    @property
    def max_seconds(self) -> float:
        return float(self.raw["segmentation"]["max_seconds"])

    @property
    def extractor(self) -> str:
        return self.raw["concepts"]["extractor"]

    @property
    def max_concepts(self) -> int:
        return int(self.raw["concepts"]["max_per_segment"])

    @property
    def llm_model(self) -> str:
        return self.raw["concepts"]["llm_model"]

    @property
    def provider(self) -> str:
        return self.raw["search"]["provider"]

    @property
    def images_per_concept(self) -> int:
        return int(self.raw["search"]["images_per_concept"])

    @property
    def safe_search(self) -> bool:
        return bool(self.raw["search"]["safe_search"])

    @property
    def download_cfg(self) -> dict:
        return self.raw["download"]

    @property
    def transcription_cfg(self) -> dict:
        return self.raw["transcription"]

    def build_query(self, concept: str) -> str:
        return self.query_template.format(concept=concept, theme=self.theme_name).strip()
