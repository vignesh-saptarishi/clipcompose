"""Tests for transcribe module.

Uses the shared source_video fixture from conftest.py.
Mocks faster-whisper and pyannote since they are optional heavy deps.
"""

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


class TestImportGuard:
    def test_missing_deps_gives_clear_error(self):
        from clipcompose.transcribe import transcribe

        with patch("clipcompose.transcribe._WHISPER_AVAILABLE", False):
            with pytest.raises(RuntimeError, match="clipcompose\\[transcribe\\]"):
                transcribe("/fake/source.mp4")


class TestExtractAudio:
    def test_extracts_wav_from_video(self, source_video, tmp_path):
        """Uses ffmpeg to extract audio from shared fixture video."""
        from clipcompose.transcribe import _extract_audio

        wav_path = _extract_audio(str(source_video), tmp_path)
        assert Path(wav_path).exists()
        assert Path(wav_path).suffix == ".wav"


class TestMergeWordsSpeakers:
    def test_assigns_speakers_to_words(self):
        from clipcompose.transcribe import _merge_words_speakers

        words = [
            {"start": 0.0, "end": 0.5, "text": "Hello"},
            {"start": 0.6, "end": 1.0, "text": "world"},
            {"start": 2.0, "end": 2.5, "text": "Goodbye"},
        ]
        # Speaker A: 0.0 - 1.5, Speaker B: 1.5 - 3.0
        speaker_segments = [
            {"speaker": "SPEAKER_00", "start": 0.0, "end": 1.5},
            {"speaker": "SPEAKER_01", "start": 1.5, "end": 3.0},
        ]
        result = _merge_words_speakers(words, speaker_segments)
        assert result[0]["speaker"] == "SPEAKER_00"
        assert result[1]["speaker"] == "SPEAKER_00"
        assert result[2]["speaker"] == "SPEAKER_01"

    def test_no_diarization_returns_null_speakers(self):
        from clipcompose.transcribe import _merge_words_speakers

        words = [
            {"start": 0.0, "end": 0.5, "text": "Hello"},
        ]
        result = _merge_words_speakers(words, None)
        assert result[0]["speaker"] is None


class TestTranscribeOutput:
    def test_output_schema(self):
        """Verify output dict has all required fields."""
        from clipcompose.transcribe import _build_output

        words = [
            {"start": 0.0, "end": 0.5, "text": "Hello", "speaker": "SPEAKER_00"},
        ]
        result = _build_output(
            source="test.mp4",
            duration_s=10.0,
            model="medium",
            language="en",
            diarized=True,
            words=words,
        )
        assert result["source"] == "test.mp4"
        assert result["duration_s"] == 10.0
        assert result["model"] == "medium"
        assert result["language"] == "en"
        assert result["diarized"] is True
        assert len(result["words"]) == 1
        # Verify it's JSON-serializable
        json.dumps(result)


class TestTranscribeIntegration:
    """Integration test: mocks whisper + pyannote but runs the full pipeline."""

    def test_full_pipeline_with_mocked_models(self, source_video, tmp_path):
        """Verify transcribe() wires audio extraction → whisper → diarize → JSON."""
        from clipcompose.transcribe import transcribe

        # Mock a whisper Word object
        mock_word_1 = MagicMock()
        mock_word_1.start = 0.0
        mock_word_1.end = 0.5
        mock_word_1.word = " Hello"

        mock_word_2 = MagicMock()
        mock_word_2.start = 0.6
        mock_word_2.end = 1.1
        mock_word_2.word = " world"

        # Mock a whisper Segment
        mock_segment = MagicMock()
        mock_segment.words = [mock_word_1, mock_word_2]

        # Mock whisper TranscriptionInfo
        mock_info = MagicMock()
        mock_info.language = "en"
        mock_info.duration = 5.0

        # Mock WhisperModel
        mock_whisper_cls = MagicMock()
        mock_whisper_instance = MagicMock()
        mock_whisper_instance.transcribe.return_value = ([mock_segment], mock_info)
        mock_whisper_cls.return_value = mock_whisper_instance

        # Mock pyannote diarization Turn objects
        mock_turn_1 = MagicMock()
        mock_turn_1.start = 0.0
        mock_turn_1.end = 1.5

        # Mock pyannote Pipeline
        mock_pyannote_cls = MagicMock()
        mock_diarization = MagicMock()
        mock_diarization.itertracks.return_value = [
            (mock_turn_1, None, "SPEAKER_00"),
        ]
        mock_pipeline_instance = MagicMock()
        mock_pipeline_instance.return_value = mock_diarization
        mock_pyannote_cls.from_pretrained.return_value = mock_pipeline_instance

        output_path = str(tmp_path / "transcript.json")

        with patch("clipcompose.transcribe._WHISPER_AVAILABLE", True), \
             patch("clipcompose.transcribe.WhisperModel", mock_whisper_cls), \
             patch("clipcompose.transcribe.PyannotePipeline", mock_pyannote_cls):
            result = transcribe(
                str(source_video),
                model="medium",
                diarize=True,
                output=output_path,
            )

        # Verify the full output
        assert result["source"] == source_video.name
        assert result["duration_s"] == 5.0
        assert result["model"] == "medium"
        assert result["language"] == "en"
        assert result["diarized"] is True
        assert len(result["words"]) == 2
        assert result["words"][0]["text"] == "Hello"
        assert result["words"][0]["speaker"] == "SPEAKER_00"

        # Verify JSON was written to disk
        assert Path(output_path).exists()
        with open(output_path) as f:
            written = json.load(f)
        assert written == result

    def test_pipeline_without_diarization(self, source_video, tmp_path):
        """Verify --no-diarize skips pyannote and sets speakers to null."""
        from clipcompose.transcribe import transcribe

        mock_word = MagicMock()
        mock_word.start = 0.0
        mock_word.end = 0.5
        mock_word.word = " Hello"

        mock_segment = MagicMock()
        mock_segment.words = [mock_word]

        mock_info = MagicMock()
        mock_info.language = "en"
        mock_info.duration = 5.0

        mock_whisper_cls = MagicMock()
        mock_whisper_instance = MagicMock()
        mock_whisper_instance.transcribe.return_value = ([mock_segment], mock_info)
        mock_whisper_cls.return_value = mock_whisper_instance

        output_path = str(tmp_path / "transcript.json")

        with patch("clipcompose.transcribe._WHISPER_AVAILABLE", True), \
             patch("clipcompose.transcribe.WhisperModel", mock_whisper_cls), \
             patch("clipcompose.transcribe.PyannotePipeline", None):
            result = transcribe(
                str(source_video),
                model="medium",
                diarize=False,
                output=output_path,
            )

        assert result["diarized"] is False
        assert result["words"][0]["speaker"] is None
