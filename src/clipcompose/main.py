"""Subcommand dispatcher for clipcompose.

Usage:
    clipcompose compose    --manifest ... --output ...
    clipcompose assemble   --manifest ... --output ...
    clipcompose transcribe source.mp4 --output transcript.json
    clipcompose cut        source.mp4 --start 10 --end 30 --output clip.mp4
"""

import argparse
import sys


def main(args=None):
    parser = argparse.ArgumentParser(
        prog="clipcompose",
        description="Manifest-driven video composition, transcription, and cutting.",
    )
    subparsers = parser.add_subparsers(dest="command")

    # Register subcommands. Each delegates to its own module's main().
    subparsers.add_parser("compose", help="Spatial composition from YAML manifest")
    subparsers.add_parser("assemble", help="Temporal assembly of pre-rendered sections")
    subparsers.add_parser("transcribe", help="Transcribe video/audio with word timestamps")
    subparsers.add_parser("cut", help="Cut clips from source video")

    # Parse only the subcommand name, pass the rest to the subcommand's parser.
    parsed, remaining = parser.parse_known_args(args)

    if parsed.command is None:
        # No subcommand given at all — show help and exit with error.
        parser.print_help()
        sys.exit(1)

    known_commands = {"compose", "assemble", "transcribe", "cut"}
    if parsed.command not in known_commands:
        parser.print_help()
        sys.exit(1)

    if parsed.command == "compose":
        from .cli import main as compose_main
        compose_main(remaining)
    elif parsed.command == "assemble":
        from .assemble_cli import main as assemble_main
        assemble_main(remaining)
    elif parsed.command == "transcribe":
        from .transcribe_cli import main as transcribe_main
        transcribe_main(remaining)
    elif parsed.command == "cut":
        from .cut_cli import main as cut_main
        cut_main(remaining)


if __name__ == "__main__":
    main()
