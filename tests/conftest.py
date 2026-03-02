"""Shared test fixtures for clipcompose tests."""

import subprocess

import pytest
import imageio_ffmpeg

_FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()


@pytest.fixture
def source_video(tmp_path):
    """Create a 5-second test video (320x240, 10fps) with audio using ffmpeg.

    Shared across test_cut.py and test_transcribe.py.
    """
    out = tmp_path / "source.mp4"
    subprocess.run(
        [
            _FFMPEG, "-y",
            "-f", "lavfi", "-i", "color=c=blue:s=320x240:d=5:r=10",
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
            "-shortest",
            "-c:v", "libx264", "-crf", "28", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "32k",
            str(out),
        ],
        check=True,
        capture_output=True,
    )
    return out
