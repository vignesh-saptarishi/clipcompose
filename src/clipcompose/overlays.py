"""Text overlay rendering for the v3 compositor.

Renders semi-transparent text overlays on top of video frames. Works at
two levels:
  - Per-clip: overlay field on clip dicts, drawn within the clip's cell.
  - Section-level: overlay field on section dicts, drawn over the full frame.

Overlays use a 3x3 grid positioning system (top-left through bottom-right)
with optional rotation (0, 90, -90 degrees).
"""

import numpy as np
from PIL import Image, ImageDraw

from .common import load_font, resolve_color


# ── Constants ────────────────────────────────────────────────────

OVERLAY_MARGIN_FRAC = 0.03       # margin from edges as fraction of frame dimension
OVERLAY_BG_ALPHA = 153           # ~60% opacity (0.6 * 255)
OVERLAY_PADDING_X = 12           # horizontal padding inside the overlay box
OVERLAY_PADDING_Y = 6            # vertical padding inside the overlay box
OVERLAY_BORDER_RADIUS = 6        # rounded corner radius


# ── Position computation ─────────────────────────────────────────


def compute_overlay_position(
    position: str,
    patch_w: int,
    patch_h: int,
    frame_w: int,
    frame_h: int,
    region: tuple[int, int, int, int] | None = None,
) -> tuple[int, int]:
    """Compute (x, y) for an overlay patch on a 3x3 grid.

    Margin is OVERLAY_MARGIN_FRAC of the region dimension from each edge.
    When *region* is None the full frame is used (backwards compatible).

    Args:
        position: One of the 9 grid positions (e.g. "top-left").
        patch_w: Rendered overlay patch width (after rotation).
        patch_h: Rendered overlay patch height (after rotation).
        frame_w: Target frame width.
        frame_h: Target frame height.
        region: Optional (rx, ry, rw, rh) sub-rectangle to constrain the
            3x3 grid to.  When None, the entire frame is used.

    Returns:
        (x, y) top-left corner for placing the overlay.
    """
    if region is not None:
        rx, ry, rw, rh = region
    else:
        rx, ry, rw, rh = 0, 0, frame_w, frame_h

    margin_x = int(rw * OVERLAY_MARGIN_FRAC)
    margin_y = int(rh * OVERLAY_MARGIN_FRAC)

    # Horizontal position.
    vert, horiz = position.split("-", 1)
    if horiz == "left":
        x = rx + margin_x
    elif horiz == "right":
        x = rx + rw - margin_x - patch_w
    else:  # center
        x = rx + (rw - patch_w) // 2

    # Vertical position.
    if vert == "top":
        y = ry + margin_y
    elif vert == "bottom":
        y = ry + rh - margin_y - patch_h
    else:  # middle
        y = ry + (rh - patch_h) // 2

    return x, y


# ── Patch rendering ──────────────────────────────────────────────


def render_overlay_patch(
    text: str,
    font_size: int,
    color: tuple[int, int, int],
    rotation: int = 0,
    bold: bool = False,
) -> np.ndarray:
    """Render overlay text on a semi-transparent dark background.

    Returns an RGBA numpy array. The background is a dark rounded-rect
    at ~60% opacity. Text is rendered in the specified color at full
    opacity. The patch is rotated if rotation != 0.

    Args:
        text: Text to render.
        font_size: Font size in pixels.
        color: RGB text color.
        rotation: 0, 90, or -90 degrees.
        bold: If True, bump font size slightly.

    Returns:
        numpy array of shape (h, w, 4), dtype uint8 (RGBA).
    """
    fs = font_size + 2 if bold else font_size
    font = load_font(fs)

    # Measure text.
    draw_tmp = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    bbox = draw_tmp.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    # Patch dimensions with padding.
    patch_w = text_w + 2 * OVERLAY_PADDING_X
    patch_h = text_h + 2 * OVERLAY_PADDING_Y

    # Create RGBA image with transparent background.
    img = Image.new("RGBA", (patch_w, patch_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Semi-transparent dark background.
    draw.rounded_rectangle(
        [(0, 0), (patch_w - 1, patch_h - 1)],
        radius=OVERLAY_BORDER_RADIUS,
        fill=(0, 0, 0, OVERLAY_BG_ALPHA),
    )

    # Draw text centered in the patch.
    tx = OVERLAY_PADDING_X
    ty = OVERLAY_PADDING_Y
    draw.text((tx, ty), text, fill=(*color, 255), font=font)

    # Apply rotation if needed.
    if rotation != 0:
        # Pillow rotates counter-clockwise, so 90 means CCW 90.
        # rotation=90 (top-to-bottom): rotate CW 90 = PIL -90 = expand
        # rotation=-90 (bottom-to-top): rotate CW -90 = PIL 90 = expand
        img = img.rotate(-rotation, expand=True, resample=Image.BICUBIC)

    return np.array(img)


# ── Frame-level overlay application ─────────────────────────────


def apply_overlays_to_frame(
    frame: np.ndarray,
    overlay_items: list[dict],
    colors: dict[str, tuple[int, int, int]],
    font_size: int,
    region: tuple[int, int, int, int] | None = None,
) -> np.ndarray:
    """Apply overlay items to a single video frame.

    Composites each overlay patch onto the frame using alpha blending.
    Called per-frame by moviepy's fl_image.

    Args:
        frame: Input frame, shape (h, w, 3), dtype uint8.
        overlay_items: List of overlay dicts (text, position, color?, weight?, rotation?).
        colors: Color palette for resolving color references.
        font_size: Base font size for overlays.
        region: Optional (rx, ry, rw, rh) sub-rectangle to constrain overlay
            positioning to.  When None, the full frame is used.

    Returns:
        Modified frame with overlays composited, same shape and dtype.
    """
    frame_h, frame_w = frame.shape[:2]
    # Work on a copy to avoid mutating the input.
    result = frame.copy()

    for item in overlay_items:
        text = item["text"]
        position = item["position"]
        rotation = item.get("rotation", 0)
        weight = item.get("weight", "normal")
        bold = weight == "bold"

        color_ref = item.get("color")
        if color_ref:
            color = resolve_color(color_ref, colors)
        else:
            color = colors.get("text", (213, 213, 211))

        # Render the overlay patch (RGBA).
        patch = render_overlay_patch(
            text, font_size, color, rotation=rotation, bold=bold,
        )
        patch_h, patch_w = patch.shape[:2]

        # Compute position on the frame (constrained to region if given).
        x, y = compute_overlay_position(
            position, patch_w, patch_h, frame_w, frame_h,
            region=region,
        )

        # Clamp to frame bounds.
        x = max(0, min(x, frame_w - patch_w))
        y = max(0, min(y, frame_h - patch_h))

        # Alpha-blend the patch onto the frame.
        alpha = patch[:, :, 3:4].astype(np.float32) / 255.0
        rgb = patch[:, :, :3].astype(np.float32)
        dest = result[y:y + patch_h, x:x + patch_w].astype(np.float32)
        blended = dest * (1 - alpha) + rgb * alpha
        result[y:y + patch_h, x:x + patch_w] = blended.astype(np.uint8)

    return result
