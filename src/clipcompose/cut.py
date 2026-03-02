"""Video cutting operations — single and batch ffmpeg cuts."""

import subprocess
from pathlib import Path

import imageio_ffmpeg

_FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()


def cut_single(
    source: str,
    start: float,
    end: float,
    output: str,
    copy: bool = False,
) -> None:
    """Cut a single segment from source video using ffmpeg.

    Args:
        source: Path to source video.
        start: Start time in seconds.
        end: End time in seconds.
        output: Output file path.
        copy: If True, stream-copy (fast, keyframe-aligned).
              If False, re-encode for frame-accurate cuts.
    """
    Path(output).parent.mkdir(parents=True, exist_ok=True)

    if copy:
        codec_args = ["-c", "copy"]
    else:
        codec_args = [
            "-c:v", "libx264", "-crf", "20", "-pix_fmt", "yuv420p",
            "-c:a", "aac",
        ]

    cmd = [
        _FFMPEG, "-y",
        "-ss", f"{start:.3f}",
        "-to", f"{end:.3f}",
        "-i", source,
        *codec_args,
        output,
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def cut_batch(
    source: str,
    cuts: list[dict],
    output_dir: str,
    copy: bool = False,
    force: bool = False,
) -> None:
    """Cut multiple segments from source video.

    Args:
        source: Path to source video.
        cuts: List of dicts with 'id', 'start', 'end'.
        output_dir: Directory for output clips (created if needed).
        copy: Stream-copy mode (see cut_single).
        force: Overwrite existing files.
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    for cut in cuts:
        out_path = out_dir / f"{cut['id']}.mp4"
        if out_path.exists() and not force:
            print(f"  SKIP   {out_path} (exists, use --force to overwrite)")
            continue

        print(f"  CUT    {cut['id']}  {cut['start']:.1f}s — {cut['end']:.1f}s")
        cut_single(source, cut["start"], cut["end"], str(out_path), copy=copy)
