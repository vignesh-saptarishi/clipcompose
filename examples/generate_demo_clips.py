#!/usr/bin/env python3
"""Generate synthetic test videos for the clipcompose demo manifests.

Creates 12 clips with varying durations in examples/demo-clips/.
Each clip is a solid color with a white "END" frame at the end,
so freeze-frames are obvious when clips have mismatched lengths.

Usage:
    python examples/generate_demo_clips.py
    # Then render:
    clipcompose --manifest examples/demo-all-templates.yaml \
        --output examples/demo-renders/ --render-all
"""

import numpy as np
from moviepy import ColorClip, CompositeVideoClip, ImageClip
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

OUTPUT_DIR = Path(__file__).resolve().parent / "demo-clips"
SIZE = (320, 240)
FPS = 30

# 12 clips with distinct colors and varying durations (1.5s to 4s).
# Duration spread means grids will show freeze-frames on shorter clips.
CLIPS = [
    ("clip-01", (180, 60, 60),   2.0),  # red
    ("clip-02", (60, 60, 180),   3.0),  # blue
    ("clip-03", (60, 160, 60),   2.5),  # green
    ("clip-04", (200, 130, 40),  1.5),  # orange
    ("clip-05", (130, 60, 180),  3.5),  # purple
    ("clip-06", (40, 170, 170),  2.0),  # cyan
    ("clip-07", (200, 200, 50),  4.0),  # yellow
    ("clip-08", (200, 80, 130),  1.5),  # pink
    ("clip-09", (50, 130, 130),  3.0),  # teal
    ("clip-10", (220, 110, 90),  2.5),  # coral
    ("clip-11", (100, 110, 130), 2.0),  # slate
    ("clip-12", (210, 180, 60),  3.5),  # gold
]


def _make_end_frame(bg_color: tuple[int, int, int]) -> np.ndarray:
    """Create an 'END' frame — white text on a dimmed version of the clip color."""
    dim = tuple(max(c // 3, 20) for c in bg_color)
    img = Image.new("RGB", SIZE, dim)
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 48
        )
    except OSError:
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), "END", font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(
        ((SIZE[0] - tw) / 2, (SIZE[1] - th) / 2),
        "END",
        fill=(255, 255, 255),
        font=font,
    )
    return np.array(img)


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, color, duration in CLIPS:
        out = OUTPUT_DIR / f"{name}.mp4"
        if out.exists():
            print(f"  skip {name} (exists)")
            continue

        # Main color body (all but last 0.5s)
        body_dur = max(duration - 0.5, 0.5)
        body = ColorClip(size=SIZE, color=color, duration=body_dur)

        # END frame (last 0.5s)
        end_frame = _make_end_frame(color)
        end_clip = ImageClip(end_frame, duration=0.5).with_start(body_dur)

        final = CompositeVideoClip([body, end_clip], size=SIZE)
        final.write_videofile(str(out), fps=FPS, logger=None)
        print(f"  wrote {name} ({duration}s)")

    print(f"\nDone. {len(CLIPS)} clips in {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
