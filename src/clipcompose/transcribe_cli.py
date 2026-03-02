"""CLI for transcription — word-level timestamps + speaker diarization.

Usage:
    clipcompose transcribe source.mp4
    clipcompose transcribe source.mp4 --model large-v3 --no-diarize
    clipcompose transcribe source.mp4 --language en --output transcript.json
"""

import argparse

from .transcribe import transcribe


def _parse_args(args=None):
    parser = argparse.ArgumentParser(
        description="Transcribe video/audio with word-level timestamps and speaker diarization.",
    )
    parser.add_argument(
        "source",
        help="Path to video or audio file",
    )
    parser.add_argument(
        "--output", default=None,
        help="Output JSON path (default: <source>.transcript.json)",
    )
    parser.add_argument(
        "--model", default="medium",
        help="Whisper model size (default: medium)",
    )
    parser.add_argument(
        "--language", default=None,
        help="Source language code (default: auto-detect)",
    )
    parser.add_argument(
        "--no-diarize", action="store_true",
        help="Skip speaker diarization",
    )
    return parser.parse_args(args)


def main(args=None):
    parsed = _parse_args(args)

    print(f"Transcribing: {parsed.source}")
    print(f"Model: {parsed.model}")
    print(f"Diarization: {'off' if parsed.no_diarize else 'on'}")

    result = transcribe(
        source=parsed.source,
        model=parsed.model,
        language=parsed.language,
        diarize=not parsed.no_diarize,
        output=parsed.output,
    )

    n_words = len(result["words"])
    n_speakers = len(set(w["speaker"] for w in result["words"] if w["speaker"]))
    print(f"\nDone: {n_words} words, {n_speakers} speakers, language={result['language']}")
    print(f"Output: {parsed.output or result['source'].rsplit('.', 1)[0] + '.transcript.json'}")


if __name__ == "__main__":
    main()
