"""Per-segment visual concept extraction.

Two backends:
- rules: proper-noun phrases first, then salient keywords (no dependencies).
- llm:   Claude picks the most *visualizable* concepts for each segment.

'auto' uses llm when ANTHROPIC_API_KEY is set, rules otherwise.
"""

from __future__ import annotations

import json
import os
import re

from .config import Config
from .segment import Window

STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "if", "then", "so", "of", "in", "on",
    "at", "to", "for", "from", "by", "with", "about", "into", "over", "after",
    "before", "between", "out", "against", "during", "without", "under",
    "is", "am", "are", "was", "were", "be", "been", "being", "do", "does",
    "did", "have", "has", "had", "will", "would", "shall", "should", "can",
    "could", "may", "might", "must", "not", "no", "yes", "this", "that",
    "these", "those", "it", "its", "he", "she", "they", "them", "his", "her",
    "their", "we", "us", "our", "you", "your", "i", "me", "my", "what",
    "which", "who", "whom", "when", "where", "why", "how", "all", "any",
    "both", "each", "few", "more", "most", "other", "some", "such", "only",
    "own", "same", "than", "too", "very", "just", "now", "also", "there",
    "here", "one", "two", "as", "because", "while", "up", "down", "really",
    "actually", "basically", "like", "get", "got", "go", "going", "went",
    "thing", "things", "way", "lot", "kind", "sort", "even", "still", "back",
    "meanwhile", "however", "eventually", "finally", "suddenly", "later",
    "again", "always", "never", "soon", "today", "yesterday", "tomorrow",
}


def extract_concepts(windows: list[Window], config: Config) -> None:
    """Fill window.concepts and window.queries in place."""
    mode = config.extractor
    if mode == "auto":
        mode = "llm" if os.environ.get("ANTHROPIC_API_KEY") else "rules"

    if mode == "llm":
        try:
            _extract_llm(windows, config)
        except Exception as exc:  # fall back rather than dying mid-pipeline
            print(f"[concepts] LLM extraction failed ({exc}); falling back to rules")
            _extract_rules(windows, config)
    elif mode == "rules":
        _extract_rules(windows, config)
    else:
        raise ValueError(f"Unknown concepts.extractor: {mode!r}")

    for window in windows:
        window.concepts = _normalize(window.concepts, config)
        window.queries = [config.build_query(c) for c in window.concepts]


def _normalize(concepts: list[str], config: Config) -> list[str]:
    aliases = config.aliases
    seen: set[str] = set()
    out: list[str] = []
    for concept in concepts:
        c = re.sub(r"\s+", " ", concept).strip().lower()
        c = re.sub(r"'s\b", "", c)
        c = aliases.get(c, c)
        if c and c not in seen:
            seen.add(c)
            out.append(c)
    return out[: config.max_concepts]


# --- rule-based ----------------------------------------------------------------

def _extract_rules(windows: list[Window], config: Config) -> None:
    boost = config.boost_terms
    for window in windows:
        text = window.text
        candidates: list[str] = []

        # 1. Proper-noun phrases (runs of capitalized words, not sentence-initial only).
        for match in re.finditer(r"\b([A-Z][a-zA-Z'\-]+(?:\s+[A-Z][a-zA-Z'\-]+)*)\b", text):
            words = match.group(1).split()
            # Trim sentence-initial/trailing capitalized stopwords ("Then Darth Vader").
            while words and words[0].lower() in STOPWORDS:
                words.pop(0)
            while words and words[-1].lower() in STOPWORDS:
                words.pop()
            if words:
                candidates.append(" ".join(words))

        # 2. Salient keywords by frequency, minus stopwords.
        tokens = [t.lower() for t in re.findall(r"[a-zA-Z'\-]{3,}", text)]
        freq: dict[str, int] = {}
        for tok in tokens:
            if tok not in STOPWORDS:
                freq[tok] = freq.get(tok, 0) + 1
        keywords = sorted(freq, key=lambda t: (-freq[t], tokens.index(t)))
        candidates.extend(keywords)

        # Rank: boosted terms first, then original order; dedupe later in _normalize.
        def rank(c: str) -> int:
            lc = c.lower()
            return 0 if any(b in lc for b in boost) else 1

        window.concepts = sorted(candidates, key=rank)


# --- LLM-based -----------------------------------------------------------------

def _extract_llm(windows: list[Window], config: Config) -> None:
    import anthropic

    client = anthropic.Anthropic()
    theme = config.theme_name or "the video's topic"

    numbered = "\n".join(f"{w.index}. [{w.start:.1f}-{w.end:.1f}s] {w.text}" for w in windows)
    prompt = f"""You are picking image-search concepts for a video edited to a narration about {theme}.

For each numbered transcript segment below, choose up to {config.max_concepts} concepts that would make strong, findable images for that exact moment. Rules:
- Prefer concrete, visual, searchable subjects: named characters, places, vehicles, objects, events, scenes.
- Use canonical full names (e.g. "darth vader", not "vader"; "millennium falcon", not "the falcon").
- Never invent things the segment does not mention or clearly imply.
- Lowercase everything. Do not include the theme name itself in the concept; it is appended automatically.

Segments:
{numbered}

Respond with ONLY a JSON object mapping segment number (as a string) to a list of concept strings, e.g. {{"1": ["death star", "darth vader"], "2": ["luke skywalker"]}}"""

    response = client.messages.create(
        model=config.llm_model,
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.content[0].text.strip()
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        raise ValueError("LLM response contained no JSON object")
    mapping = json.loads(match.group(0))

    for window in windows:
        concepts = mapping.get(str(window.index), [])
        if not isinstance(concepts, list):
            concepts = []
        window.concepts = [str(c) for c in concepts]
