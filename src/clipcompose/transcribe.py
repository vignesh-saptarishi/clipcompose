"""Transcription pipeline — faster-whisper + pyannote diarization.

Requires optional dependencies: pip install clipcompose[transcribe]
Import-guarded so the rest of clipcompose works without torch.
"""

import json
import subprocess
from pathlib import Path

import imageio_ffmpeg

_FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

# Import-guarded heavy dependencies.
try:
    from faster_whisper import WhisperModel
    from pyannote.audio import Pipeline as PyannotePipeline
    _WHISPER_AVAILABLE = True
except ImportError:
    WhisperModel = None
    PyannotePipeline = None
    _WHISPER_AVAILABLE = False


def _extract_audio(source: str, work_dir: Path) -> str:
    """Extract audio from video to WAV using ffmpeg.

    Returns path to the extracted WAV file.
    """
    wav_path = str(work_dir / "audio.wav")
    cmd = [
        _FFMPEG, "-y",
        "-i", source,
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", "16000",
        "-ac", "1",
        wav_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return wav_path


def _merge_words_speakers(
    words: list[dict],
    speaker_segments: list[dict] | None,
) -> list[dict]:
    """Assign speaker labels to words based on timestamp overlap.

    If speaker_segments is None (no diarization), all speakers are set to None.
    """
    if speaker_segments is None:
        return [{**w, "speaker": None} for w in words]

    result = []
    for word in words:
        mid = (word["start"] + word["end"]) / 2
        speaker = None
        for seg in speaker_segments:
            if seg["start"] <= mid <= seg["end"]:
                speaker = seg["speaker"]
                break
        result.append({**word, "speaker": speaker})
    return result


def _build_output(
    source: str,
    duration_s: float,
    model: str,
    language: str,
    diarized: bool,
    words: list[dict],
) -> dict:
    """Build the output dict matching the transcript JSON schema."""
    return {
        "source": source,
        "duration_s": duration_s,
        "model": model,
        "language": language,
        "diarized": diarized,
        "words": words,
    }


def transcribe(
    source: str,
    model: str = "medium",
    language: str | None = None,
    diarize: bool = True,
    output: str | None = None,
) -> dict:
    """Run transcription pipeline on a video/audio file.

    Args:
        source: Path to video or audio file.
        model: Whisper model size (tiny, base, small, medium, large-v3).
        language: Language code or None for auto-detection.
        diarize: Whether to run speaker diarization.
        output: Output JSON path. If None, uses <source-stem>.transcript.json.

    Returns:
        Transcript dict (also written to output path).

    Raises:
        RuntimeError: If clipcompose[transcribe] is not installed.
    """
    if not _WHISPER_AVAILABLE:
        raise RuntimeError(
            "Transcription requires extra dependencies.\n"
            "Run: pip install clipcompose[transcribe]"
        )

    import tempfile

    source_path = Path(source)
    if output is None:
        output = str(source_path.with_suffix("").with_suffix(".transcript.json"))

    # Step 1: extract audio to temp WAV.
    with tempfile.TemporaryDirectory() as work_dir:
        wav_path = _extract_audio(source, Path(work_dir))

        # Step 2: run faster-whisper.
        whisper_model = WhisperModel(model)
        segments, info = whisper_model.transcribe(
            wav_path,
            language=language,
            word_timestamps=True,
        )

        words = []
        for segment in segments:
            if segment.words:
                for w in segment.words:
                    words.append({
                        "start": round(w.start, 3),
                        "end": round(w.end, 3),
                        "text": w.word.strip(),
                    })

        detected_language = language or info.language
        duration_s = info.duration

        # Step 3: diarization (optional).
        speaker_segments = None
        if diarize:
            pipeline = PyannotePipeline.from_pretrained(
                "pyannote/speaker-diarization-3.1",
            )
            diarization = pipeline(wav_path)
            speaker_segments = []
            for turn, _, speaker in diarization.itertracks(yield_label=True):
                speaker_segments.append({
                    "speaker": speaker,
                    "start": round(turn.start, 3),
                    "end": round(turn.end, 3),
                })

    # Step 4: merge words with speakers.
    words = _merge_words_speakers(words, speaker_segments)

    # Step 5: build and write output.
    result = _build_output(
        source=str(source_path.name),
        duration_s=round(duration_s, 1),
        model=model,
        language=detected_language,
        diarized=diarize,
        words=words,
    )

    Path(output).parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w") as f:
        json.dump(result, f, indent=2)

    return result
