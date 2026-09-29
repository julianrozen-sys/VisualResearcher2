"""Image search providers. Each returns a list of result dicts:

{"url": ..., "title": ..., "source": ..., "query": ..., "concept": ...}
"""

from __future__ import annotations

import os

import requests

from .config import Config


def search_images(query: str, concept: str, config: Config) -> list[dict]:
    provider = config.provider
    if provider == "duckduckgo":
        results = _search_duckduckgo(query, config)
    elif provider == "google":
        results = _search_google(query, config)
    else:
        raise ValueError(f"Unknown search.provider: {provider!r}")

    filtered = []
    for r in results:
        haystack = f"{r.get('title', '')} {r.get('url', '')}".lower()
        if any(term in haystack for term in config.exclude_terms):
            continue
        r["query"] = query
        r["concept"] = concept
        filtered.append(r)
    return filtered[: config.images_per_concept]


def _search_duckduckgo(query: str, config: Config) -> list[dict]:
    try:
        from ddgs import DDGS
    except ImportError as exc:
        raise RuntimeError("DuckDuckGo search requires the ddgs package: pip install ddgs") from exc

    safesearch = "moderate" if config.safe_search else "off"
    # Over-fetch so exclude_terms filtering still leaves enough results.
    want = config.images_per_concept * 4
    with DDGS() as ddgs:
        raw = ddgs.images(query, safesearch=safesearch, max_results=want)
    return [
        {"url": r.get("image"), "title": r.get("title", ""), "source": r.get("url", "")}
        for r in (raw or [])
        if r.get("image")
    ]


def _search_google(query: str, config: Config) -> list[dict]:
    api_key = os.environ.get("GOOGLE_API_KEY")
    cse_id = os.environ.get("GOOGLE_CSE_ID")
    if not api_key or not cse_id:
        raise RuntimeError("Google provider needs GOOGLE_API_KEY and GOOGLE_CSE_ID env vars")

    resp = requests.get(
        "https://www.googleapis.com/customsearch/v1",
        params={
            "key": api_key,
            "cx": cse_id,
            "q": query,
            "searchType": "image",
            "num": min(10, config.images_per_concept * 3),
            "safe": "active" if config.safe_search else "off",
        },
        timeout=20,
    )
    resp.raise_for_status()
    items = resp.json().get("items", [])
    return [
        {
            "url": item.get("link"),
            "title": item.get("title", ""),
            "source": item.get("image", {}).get("contextLink", ""),
        }
        for item in items
        if item.get("link")
    ]
