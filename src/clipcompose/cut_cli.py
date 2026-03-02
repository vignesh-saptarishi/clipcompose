"""CLI for video cutting — single cut or batch from YAML manifest.

Usage:
    # Single cut
    clipcompose cut source.mp4 --start 10 --end 30 --output clip.mp4

    # Batch cuts
    clipcompose cut source.mp4 --manifest cuts.yaml --output-dir clips/
    clipcompose cut --manifest cuts.yaml --output-dir clips/
"""

import argparse
from pathlib import Path

from .cut import cut_single, cut_batch
from .cuts_manifest import load_cuts_manifest


def main(args=None):
    parser = argparse.ArgumentParser(
        description="Cut clips from a source video.",
    )
    parser.add_argument(
        "source", nargs="?", default=None,
        help="Path to source video (optional if --manifest provides it)",
    )
    parser.add_argument(
        "--start", type=float, default=None,
        help="Start time in seconds (single cut mode)",
    )
    parser.add_argument(
        "--end", type=float, default=None,
        help="End time in seconds (single cut mode)",
    )
    parser.add_argument(
        "--output", default=None,
        help="Output file path (single cut mode)",
    )
    parser.add_argument(
        "--manifest", default=None,
        help="Path to cuts YAML manifest (batch mode)",
    )
    parser.add_argument(
        "--output-dir", default=None,
        help="Output directory for batch cuts",
    )
    parser.add_argument(
        "--copy", action="store_true",
        help="Stream-copy (fast, keyframe-aligned) instead of re-encode",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Overwrite existing output files",
    )
    parsed = parser.parse_args(args)

    # Determine mode: single vs batch.
    is_single = parsed.start is not None or parsed.end is not None or parsed.output is not None
    is_batch = parsed.manifest is not None or parsed.output_dir is not None

    if is_single and is_batch:
        parser.error(
            "Cannot mix single-cut args (--start/--end/--output) "
            "with batch args (--manifest/--output-dir)"
        )

    if is_single:
        if parsed.start is None or parsed.end is None or parsed.output is None:
            parser.error("Single cut mode requires --start, --end, and --output")
        if parsed.source is None:
            parser.error("Single cut mode requires a source video argument")

        print(f"Cutting {parsed.source}  {parsed.start:.1f}s — {parsed.end:.1f}s")
        cut_single(
            parsed.source, parsed.start, parsed.end, parsed.output,
            copy=parsed.copy,
        )
        print(f"Done: {parsed.output}")

    elif is_batch:
        if parsed.manifest is None:
            parser.error("Batch mode requires --manifest")
        if parsed.output_dir is None:
            parser.error("Batch mode requires --output-dir")

        config = load_cuts_manifest(parsed.manifest)

        # CLI source arg overrides manifest source.
        source = parsed.source or config["source"]

        # Validate the final resolved source, not the manifest's.
        if not Path(source).exists():
            raise FileNotFoundError(f"Source video not found: {source}")

        print(f"Batch cutting {len(config['cuts'])} segments from {source}")
        cut_batch(
            source, config["cuts"], parsed.output_dir,
            copy=parsed.copy, force=parsed.force,
        )
        print(f"Done: {len(config['cuts'])} clips in {parsed.output_dir}")

    else:
        parser.error("Specify either single cut (--start/--end/--output) or batch (--manifest/--output-dir)")


if __name__ == "__main__":
    main()
