"""Tests for cut operations.

Uses the shared source_video fixture from conftest.py.
Uses moviepy for duration probing (imageio_ffmpeg does NOT bundle ffprobe).
"""

from pathlib import Path

import pytest
from moviepy import VideoFileClip


def _get_duration(path):
    """Probe video duration using moviepy (same approach as assemble_cli.py)."""
    with VideoFileClip(str(path)) as clip:
        return clip.duration


class TestCutSingle:
    def test_basic_cut(self, source_video, tmp_path):
        from clipcompose.cut import cut_single

        out = tmp_path / "clip.mp4"
        cut_single(str(source_video), 1.0, 3.0, str(out))
        assert out.exists()
        dur = _get_duration(out)
        assert 1.5 < dur < 2.5  # ~2 seconds, some tolerance for codec

    def test_copy_mode(self, source_video, tmp_path):
        from clipcompose.cut import cut_single

        out = tmp_path / "clip-copy.mp4"
        cut_single(str(source_video), 0.0, 3.0, str(out), copy=True)
        assert out.exists()

    def test_preserves_audio(self, source_video, tmp_path):
        from clipcompose.cut import cut_single

        out = tmp_path / "clip.mp4"
        cut_single(str(source_video), 1.0, 3.0, str(out))
        # moviepy's AudioFileClip will be non-None if audio exists
        with VideoFileClip(str(out)) as clip:
            assert clip.audio is not None

    def test_creates_parent_dirs(self, source_video, tmp_path):
        from clipcompose.cut import cut_single

        out = tmp_path / "nested" / "dir" / "clip.mp4"
        cut_single(str(source_video), 0.0, 2.0, str(out))
        assert out.exists()


class TestCutBatch:
    def test_batch_creates_all_files(self, source_video, tmp_path):
        from clipcompose.cut import cut_batch

        cuts = [
            {"id": "seg-001", "start": 0.0, "end": 2.0},
            {"id": "seg-002", "start": 2.0, "end": 4.0},
        ]
        out_dir = tmp_path / "clips"
        cut_batch(str(source_video), cuts, str(out_dir))
        assert (out_dir / "seg-001.mp4").exists()
        assert (out_dir / "seg-002.mp4").exists()

    def test_skips_existing_files(self, source_video, tmp_path):
        from clipcompose.cut import cut_batch

        out_dir = tmp_path / "clips"
        out_dir.mkdir()
        existing = out_dir / "seg-001.mp4"
        existing.write_text("placeholder")  # fake existing file

        cuts = [
            {"id": "seg-001", "start": 0.0, "end": 2.0},
            {"id": "seg-002", "start": 2.0, "end": 4.0},
        ]
        cut_batch(str(source_video), cuts, str(out_dir))
        # seg-001 should NOT be overwritten
        assert existing.read_text() == "placeholder"
        assert (out_dir / "seg-002.mp4").exists()

    def test_force_overwrites(self, source_video, tmp_path):
        from clipcompose.cut import cut_batch

        out_dir = tmp_path / "clips"
        out_dir.mkdir()
        existing = out_dir / "seg-001.mp4"
        existing.write_text("placeholder")

        cuts = [{"id": "seg-001", "start": 0.0, "end": 2.0}]
        cut_batch(str(source_video), cuts, str(out_dir), force=True)
        # Should be a real video now, not "placeholder"
        assert existing.stat().st_size > 100
