"""CLI entry point: python -m visualresearcher run <audio> --config configs/starwars.yaml"""

from __future__ import annotations

import argparse
import sys

from .config import Config
from .pipeline import run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="visualresearcher",
        description="Transcribe audio and research themed images per time segment.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="Run the full pipeline")
    run_p.add_argument("audio", nargs="?", help="Audio file (mp3/wav/m4a/...)")
    run_p.add_argument("--transcript", help="Existing transcript JSON (skips transcription)")
    run_p.add_argument("--config", help="Project YAML config (e.g. configs/starwars.yaml)")
    run_p.add_argument("--out", default="output", help="Output directory (default: output/)")
    run_p.add_argument("--dry-run", action="store_true",
                       help="Build segments and queries but fetch nothing")
    run_p.add_argument("--transcriber", choices=["openai", "local"],
                       help="Override transcription backend from the config")

    args = parser.parse_args(argv)

    if args.command == "run":
        if not args.audio and not args.transcript:
            run_p.error("provide an audio file or --transcript")
        config = Config.load(args.config)
        if args.transcriber:
            config.raw["transcription"]["transcriber"] = args.transcriber
        try:
            run(args.audio, args.transcript, config, args.out, dry_run=args.dry_run)
        except (RuntimeError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
