# VisualResearcher

Turn an audio track into a time-coded visual shot list, automatically.

Give it an audio file. It:

1. **Transcribes** the audio with word/segment timestamps (OpenAI Whisper API or local `faster-whisper`).
2. **Segments** the transcript into configurable time windows (default **7–9 seconds**, tuned for cut-length editing).
3. **Extracts visual concepts** per segment — proper names first (characters, places, ships), then salient keywords. Optionally uses Claude for much more accurate concept extraction.
4. **Builds themed search queries** so you never get random results: every query is rendered through a template such as `"{concept} star wars"`.
5. **Fetches images** per segment from pluggable providers (DuckDuckGo works with no API key; Google Custom Search supported), filters and downloads them into one folder per segment, and writes a `manifest.json` you can drive an editor or downstream tool with.

Everything — theme, segment length, query template, providers, filters, image counts — lives in a YAML project config. The Star Wars setup is just `configs/starwars.yaml`; make a new YAML to point the same pipeline at any other topic.

## Install

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# optional extras
pip install faster-whisper   # local transcription (no OpenAI key needed)
pip install anthropic        # Claude-powered concept extraction
```

## Quick start (Star Wars project)

```bash
export OPENAI_API_KEY=sk-...        # for Whisper API transcription (or use --transcriber local)
export ANTHROPIC_API_KEY=sk-ant-... # optional, enables LLM concept extraction

python -m visualresearcher run narration.mp3 --config configs/starwars.yaml --out output/
```

Output layout:

```
output/
  transcript.json            # raw timestamped transcript
  manifest.json              # segments, concepts, queries, image files
  segments/
    001_0.0-8.4/
      segment.json
      01_death-star.jpg
      02_death-star.jpg
      03_darth-vader.jpg
    002_8.4-16.9/
      ...
```

If you already have a transcript, skip transcription:

```bash
python -m visualresearcher run --transcript output/transcript.json --config configs/starwars.yaml --out output/
```

Dry run (build segments + queries, fetch nothing):

```bash
python -m visualresearcher run narration.mp3 --config configs/starwars.yaml --dry-run
```

## Configuration

All knobs are YAML (see `configs/starwars.yaml` and `configs/default.yaml`):

```yaml
theme:
  name: star wars                    # appended to every query
  query_template: "{concept} star wars"   # exact query shape
  aliases:                           # normalize spoken names -> canonical search names
    vader: darth vader
    the emperor: emperor palpatine
  boost_terms: [jedi, sith, darth]   # concepts containing these rank higher
  exclude_terms: [lego, funko, toy, cake, costume, meme]  # drop noisy results

segmentation:
  min_seconds: 7
  max_seconds: 9

concepts:
  extractor: auto        # auto | llm | rules  (auto = llm if key present, else rules)
  max_per_segment: 3

search:
  provider: duckduckgo   # duckduckgo | google
  images_per_concept: 3
  safe_search: true

download:
  enabled: true
  timeout_seconds: 15
  min_bytes: 15000       # skip thumbnails/broken files
  max_images_per_segment: 6
```

To build a project for a different topic, copy the YAML and change `theme` —
the pipeline itself never hardcodes Star Wars.

## Providers

| Provider | Key needed | Notes |
|---|---|---|
| `duckduckgo` | none | default; uses the `ddgs` package |
| `google` | `GOOGLE_API_KEY` + `GOOGLE_CSE_ID` | Google Custom Search (image mode) |

## Transcribers

| Name | Requirement | Notes |
|---|---|---|
| `openai` | `OPENAI_API_KEY` | Whisper API, `verbose_json` with segment timestamps |
| `local` | `pip install faster-whisper` | runs on-device, no key |
| `--transcript file.json` | — | reuse an existing transcript |
