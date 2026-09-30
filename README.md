# VisualResearcher

Turn an audio track into a time-coded visual shot list, automatically.

Give it an audio file. It:

1. **Transcribes** the audio with segment timestamps (OpenAI Whisper API or local `faster-whisper`). Files of any size work: big audio or video is automatically split at natural pauses, transcribed in pieces, and stitched back onto the original timeline.
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

## Large files

The OpenAI API rejects uploads over 25 MB, so this tool handles size for you. Any file over
`transcription.max_direct_mb` (default 20 MB), or in a format the API doesn't accept, is converted by
ffmpeg to small mono speech-quality audio (about 0.24 MB per minute) and cut into ~10 minute chunks.
Cuts are placed in the middle of pauses so words aren't sliced. Each chunk is transcribed and its
timestamps are shifted back onto the original timeline.

- **Any input:** wav, flac, mp3, m4a, and even video files (the audio track is extracted). Multi-hour
  and multi-GB files work; memory use stays flat because ffmpeg streams the audio.
- **No ffmpeg install needed:** `imageio-ffmpeg` (in `requirements.txt`) bundles a copy. A system
  ffmpeg is used if you have one.
- **Resumable:** finished chunks are cached in `<out>/_work/chunks/`. If a run is interrupted (network
  drop, closed laptop), re-run the same command and it continues without re-paying for transcribed
  audio. Delete `<out>/_work` afterwards to reclaim the space.
- **Retries:** each chunk is retried up to 3 times with backoff on API errors.
- **Tuning:** `transcription.chunk_minutes` (default 10) and `transcription.max_direct_mb`.
- **Cost:** Whisper API is billed per minute of audio, so a 2-hour file costs about $0.72.
- `--transcriber local` (faster-whisper) has no size limit either and needs no key.

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
