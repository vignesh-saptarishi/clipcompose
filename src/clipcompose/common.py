"""compositor.common — shared utilities for video composition.

Contains: color parsing, path variable resolution, font loading,
text rendering, and clip loading.
Cherry-picked from v1 video_templates.common (stable, tested functions).
"""

import re
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from moviepy import VideoFileClip


# ── Font paths ─────────────────────────────────────────────────────
# Inter preferred for clean research visuals, DejaVu Sans as fallback.

FONT_PATHS = [
    Path.home() / ".local/share/fonts/Inter.ttc",
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
]


# ── Color utilities ────────────────────────────────────────────────

def parse_hex_color(hex_str: str) -> tuple[int, int, int]:
    """Convert '#RRGGBB' or 'RRGGBB' string to (R, G, B) tuple."""
    hex_str = hex_str.lstrip("#")
    return (int(hex_str[0:2], 16), int(hex_str[2:4], 16), int(hex_str[4:6], 16))


def resolve_color(
    value: str, palette: dict[str, tuple[int, int, int]],
) -> tuple[int, int, int]:
    """Resolve a color reference — palette key name or inline '#RRGGBB'.

    Palette keys are tried first. If the value starts with '#' or is 6 hex
    chars, it's parsed as inline hex. Otherwise raises ValueError.
    """
    if value in palette:
        return palette[value]
    if value.startswith("#") or (
        len(value) == 6
        and all(c in "0123456789abcdefABCDEF" for c in value)
    ):
        return parse_hex_color(value)
    raise ValueError(
        f"Unknown color: '{value}'. Not in palette and not a hex value."
    )


# ── Path utilities ─────────────────────────────────────────────────

def resolve_path_vars(text: str, paths: dict[str, str]) -> str:
    """Replace ${name} variables in a string using the paths dict."""
    def _replace(match):
        key = match.group(1)
        if key not in paths:
            raise ValueError(f"Unknown path variable: ${{{key}}}")
        return paths[key]
    return re.sub(r"\$\{(\w+)\}", _replace, text)


# ── Font loading ───────────────────────────────────────────────────

def load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Load Inter (or fallback) at the given size.

    Inter.ttc is a font collection. Index 0 = Regular, index 1 = Italic.
    For bold, callers increase the size slightly since Inter.ttc doesn't
    have a separate bold face accessible by index in Pillow.
    """
    for font_path in FONT_PATHS:
        if font_path.exists():
            try:
                return ImageFont.truetype(str(font_path), size=size, index=0)
            except (OSError, IndexError):
                continue
    # Last resort: Pillow default bitmap font.
    return ImageFont.load_default()


# ── Text rendering ─────────────────────────────────────────────────

def render_text_on_image(
    img: Image.Image,
    text: str,
    position: tuple[int, int],
    font: ImageFont.FreeTypeFont,
    color: tuple[int, int, int],
    align: str = "left",
    max_width: int | None = None,
) -> int:
    """Draw text on a Pillow image and return the text height.

    If max_width is set and text exceeds it, the text is truncated
    with an ellipsis so it fits within the specified pixel width.
    """
    draw = ImageDraw.Draw(img)

    if max_width:
        bbox = draw.textbbox((0, 0), text, font=font)
        while (bbox[2] - bbox[0]) > max_width and len(text) > 5:
            text = text[:-4] + "..."
            bbox = draw.textbbox((0, 0), text, font=font)

    draw.text(position, text, fill=color, font=font, align=align)
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[3] - bbox[1]


# ── Clip loading ───────────────────────────────────────────────────

def load_clip(path: str | Path, target_fps: int) -> VideoFileClip:
    """Load a single mp4 clip and resample to target fps.

    Source clips may be recorded at different fps (e.g. 50fps from the
    environment renderer). This normalizes to the manifest's target fps.
    """
    clip = VideoFileClip(str(path))
    if clip.fps != target_fps:
        clip = clip.with_fps(target_fps)
    return clip
