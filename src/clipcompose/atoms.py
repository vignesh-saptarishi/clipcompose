"""AnnotatedClip atom — the fundamental building block of the v3 compositor.

An AnnotatedClip is a video clip with a flush annotation band forming one
visual rectangle. The band sits directly against the clip edge — no gap.
Together they look like a single object.

The video + band form a tight "unit" that is centered within the bounding
box. The band's perpendicular dimension matches the video exactly, so the
unit is one clean rectangle — no stretching, no dead space between them.

The annotation band contains a list of annotation lines. Each line has:
  - text: the string to render.
  - color (optional): hex string or palette key. Defaults to text_secondary.
  - weight (optional): "normal" or "bold". Bold gets a font size bump.

All pixel dimensions (font sizes, padding, spacing, border) scale
proportionally with the atom's bounding box height. Constants are
defined at a reference height of 900px (single-clip in 1080p) and
scaled linearly for other sizes. This ensures atoms look consistent
whether rendered as a full-screen single clip or a small grid cell.

Usage:
  # Static frame (for compositing behind the video clip):
  frame = render_annotated_clip_frame(bbox_w, bbox_h, side, annotations, ...,
                                       src_w=640, src_h=480)

  # Full moviepy composite (video + annotation layer):
  clip = render_annotated_clip(clip_config, bbox, colors, fps)
"""

import numpy as np
from PIL import Image, ImageDraw
from moviepy import ImageClip, CompositeVideoClip

from .common import load_font, load_clip, resolve_color
from .overlays import apply_overlays_to_frame


# ── Scaling system ───────────────────────────────────────────────
#
# All pixel constants are defined at REF_H (900px, which is the
# atom bbox_h for a single-clip section in 1080p after header and
# padding). At other sizes they scale linearly, with a floor to
# prevent values from becoming invisible or unreadable.

REF_H = 900  # reference bbox height in pixels

# Pixel values at reference height. Each is (value_at_900px, floor).
_REF_FONT_SIZE = (22, 8)
_REF_FONT_BOLD_BUMP = (2, 1)
_REF_BAND_PADDING_X = (12, 4)
_REF_BAND_PADDING_Y = (8, 3)
_REF_BAND_MIN_PX = (60, 20)
_REF_BORDER_WIDTH = (2, 1)
_REF_LINE_SPACING_SIDE = (12, 4)
_REF_LINE_SPACING_TOPBOT = (4, 2)
_REF_BG_OFFSET = (14, 6)

# Band sizing constraints (fractions — already relative).
BAND_MIN_FRAC = 0.08
BAND_MAX_FRAC = 0.40


def _scale(ref_and_floor: tuple[int, int], bbox_h: int) -> int:
    """Scale a reference pixel value to the current bbox height.

    Args:
        ref_and_floor: (value_at_REF_H, absolute_minimum).
        bbox_h: Current bounding box height.

    Returns:
        Scaled pixel value, at least the floor.
    """
    ref_val, floor = ref_and_floor
    return max(floor, round(ref_val * bbox_h / REF_H))


def _compute_layout_params(bbox_h: int) -> dict[str, int]:
    """Compute all scaled layout parameters for a given bbox height.

    Returns a dict with all pixel values ready to use. Computed once
    per atom and passed through the band dict so every function can
    access them without re-computing.
    """
    return {
        "font_size": _scale(_REF_FONT_SIZE, bbox_h),
        "font_bold_bump": _scale(_REF_FONT_BOLD_BUMP, bbox_h),
        "band_padding_x": _scale(_REF_BAND_PADDING_X, bbox_h),
        "band_padding_y": _scale(_REF_BAND_PADDING_Y, bbox_h),
        "band_min_px": _scale(_REF_BAND_MIN_PX, bbox_h),
        "border_width": _scale(_REF_BORDER_WIDTH, bbox_h),
        "line_spacing_side": _scale(_REF_LINE_SPACING_SIDE, bbox_h),
        "line_spacing_topbot": _scale(_REF_LINE_SPACING_TOPBOT, bbox_h),
        "bg_offset": _scale(_REF_BG_OFFSET, bbox_h),
    }


# ── Layout computation ────────────────────────────────────────────


def _build_lines(
    annotations: list[dict],
    colors: dict[str, tuple[int, int, int]],
    font_size: int,
    bold_size: int,
) -> list[tuple[str, any, tuple[int, int, int]]]:
    """Build renderable (text, font, color) tuples from annotation dicts.

    Each annotation dict has:
      - text (str): required.
      - color (str, optional): hex string or palette key.
      - weight (str, optional): "normal" or "bold".
    """
    lines = []
    default_color = colors.get("text_secondary", (136, 136, 136))

    for annot in annotations:
        text = annot["text"]
        weight = annot.get("weight", "normal")
        fs = bold_size if weight == "bold" else font_size
        font = load_font(fs)

        color_ref = annot.get("color")
        if color_ref:
            text_color = resolve_color(color_ref, colors)
        else:
            text_color = default_color

        lines.append((text, font, text_color))

    return lines


def compute_annotation_band(
    side: str,
    annotations: list[dict],
    bbox_w: int,
    bbox_h: int,
    colors: dict[str, tuple[int, int, int]],
    src_w: int = 0,
    src_h: int = 0,
) -> dict:
    """Compute annotation band dimensions and unit-centered layout.

    The video + annotation band form a tight visual unit. This function
    computes the band thickness from text, scales the video to fit the
    remaining space, then sizes the band's perpendicular dimension to
    match the video. The resulting unit is centered in the bounding box.

    All pixel values scale with bbox_h relative to REF_H (900px).

    Args:
        side: "left", "right", "above", or "below".
        annotations: List of annotation dicts (text, optional color/weight).
        bbox_w: Bounding box width (total space available).
        bbox_h: Bounding box height.
        colors: Palette dict with color keys for annotation resolution.
        src_w: Source video width (0 = fill available space).
        src_h: Source video height (0 = fill available space).

    Returns:
        Dict with layout geometry, rendered lines, and scaled params.
    """
    # Compute all scaled layout parameters for this bbox size.
    lp = _compute_layout_params(bbox_h)

    font_size = lp["font_size"]
    bold_size = font_size + lp["font_bold_bump"]

    # Build text lines from annotation dicts.
    lines = _build_lines(annotations, colors, font_size, bold_size)

    # Measure text dimensions.
    draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    max_text_w = 0
    total_text_h = 0
    line_spacing = lp["line_spacing_side"] if side in ("left", "right") else lp["line_spacing_topbot"]
    for text, font, _ in lines:
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        max_text_w = max(max_text_w, tw)
        total_text_h += th
    if lines:
        total_text_h += line_spacing * (len(lines) - 1)

    # Compute band size based on side orientation.
    is_horizontal = side in ("left", "right")
    has_video_dims = src_w > 0 and src_h > 0

    if is_horizontal:
        # Step 1: Band thickness (width) from text content, clamped.
        raw_band_w = max_text_w + 2 * lp["band_padding_x"]
        min_band = max(lp["band_min_px"], int(bbox_w * BAND_MIN_FRAC))
        max_band = int(bbox_w * BAND_MAX_FRAC)
        band_w = max(min_band, min(max_band, raw_band_w))

        # Step 2: Scale video to fit remaining space.
        # Reserve border margin so top/bottom borders stay visible.
        avail_w = bbox_w - band_w
        avail_h = bbox_h - 2 * lp["border_width"]
        if has_video_dims:
            scale = min(avail_w / src_w, avail_h / src_h)
            clip_w = int(src_w * scale)
            clip_h = int(src_h * scale)
        else:
            clip_w = avail_w
            clip_h = avail_h

        # Step 3: Band height matches video height (tight unit).
        band_h = clip_h

        # Step 4: Unit dimensions and centering.
        unit_w = clip_w + band_w
        unit_h = clip_h
        unit_x = (bbox_w - unit_w) // 2
        unit_y = (bbox_h - unit_h) // 2

        # Step 5: Absolute positions within the bbox.
        if side == "left":
            band_x = unit_x
            band_y = unit_y
            clip_x = unit_x + band_w
            clip_y = unit_y
        else:  # right
            clip_x = unit_x
            clip_y = unit_y
            band_x = unit_x + clip_w
            band_y = unit_y
    else:
        # Step 1: Band thickness (height) from text content, clamped.
        raw_band_h = total_text_h + 2 * lp["band_padding_y"]
        min_band = max(lp["band_min_px"], int(bbox_h * BAND_MIN_FRAC))
        max_band = int(bbox_h * BAND_MAX_FRAC)
        band_h = max(min_band, min(max_band, raw_band_h))

        # Step 2: Scale video to fit remaining space.
        avail_w = bbox_w
        avail_h = bbox_h - band_h
        if has_video_dims:
            scale = min(avail_w / src_w, avail_h / src_h)
            clip_w = int(src_w * scale)
            clip_h = int(src_h * scale)
        else:
            clip_w = avail_w
            clip_h = avail_h

        # Step 3: Band width matches video width (tight unit).
        band_w = clip_w

        # Step 4: Unit dimensions and centering.
        unit_w = clip_w
        unit_h = clip_h + band_h
        unit_x = (bbox_w - unit_w) // 2
        unit_y = (bbox_h - unit_h) // 2

        # Step 5: Absolute positions within the bbox.
        if side == "above":
            band_x = unit_x
            band_y = unit_y
            clip_x = unit_x
            clip_y = unit_y + band_h
        else:  # below
            clip_x = unit_x
            clip_y = unit_y
            band_x = unit_x
            band_y = unit_y + clip_h

    return {
        "band_w": band_w,
        "band_h": band_h,
        "band_x": band_x,
        "band_y": band_y,
        "clip_x": clip_x,
        "clip_y": clip_y,
        "clip_w": clip_w,
        "clip_h": clip_h,
        "unit_x": unit_x,
        "unit_y": unit_y,
        "unit_w": unit_w,
        "unit_h": unit_h,
        "lines": lines,
        "font_size": font_size,
        "lp": lp,  # scaled layout params for use by renderers
    }


# ── Static frame rendering ───────────────────────────────────────


def render_annotated_clip_frame(
    bbox_w: int,
    bbox_h: int,
    side: str,
    annotations: list[dict],
    bg_color: tuple[int, int, int],
    colors: dict[str, tuple[int, int, int]],
    src_w: int = 0,
    src_h: int = 0,
) -> np.ndarray:
    """Render the static annotation layer as a numpy frame.

    This produces the background + annotation text. The actual video clip
    is composited on top of this by the caller (render_annotated_clip).

    The band region gets a subtle background tint (bg_offset lighter
    than the section background) so it reads as part of the clip object.

    Args:
        bbox_w, bbox_h: Bounding box dimensions.
        side: Annotation side.
        annotations: List of annotation dicts.
        bg_color: Section background RGB.
        colors: Color palette.
        src_w, src_h: Source video dimensions for unit-centering.

    Returns:
        numpy array of shape (bbox_h, bbox_w, 3), dtype uint8.
    """
    band = compute_annotation_band(
        side, annotations, bbox_w, bbox_h, colors, src_w, src_h,
    )
    lp = band["lp"]

    # Create the frame at the bounding box size with section background.
    img = Image.new("RGB", (bbox_w, bbox_h), bg_color)
    draw = ImageDraw.Draw(img)

    # Band background: slightly lighter than section bg.
    band_bg = tuple(min(255, c + lp["bg_offset"]) for c in bg_color)

    # Draw the band background rectangle at its computed position.
    bx, by = band["band_x"], band["band_y"]
    draw.rectangle(
        [(bx, by), (bx + band["band_w"], by + band["band_h"])],
        fill=band_bg,
    )

    # Draw text lines centered in the band.
    _draw_band_text(draw, band, side)

    # Border around the tight unit (video + band) using accent color.
    accent = colors.get("accent", (177, 19, 77))
    ux, uy = band["unit_x"], band["unit_y"]
    uw, uh = band["unit_w"], band["unit_h"]
    draw.rectangle(
        [(ux, uy), (ux + uw, uy + uh)],
        outline=accent,
        width=lp["border_width"],
    )

    return np.array(img)


def _draw_band_text(
    draw: ImageDraw.ImageDraw,
    band: dict,
    side: str,
) -> None:
    """Draw annotation text lines centered within the band area.

    For left/right bands: text is vertically centered, left-aligned
    with band_padding_x from the band's left edge.

    For above/below bands: text is horizontally centered, vertically
    centered within the band height.
    """
    lines = band["lines"]
    if not lines:
        return

    lp = band["lp"]
    line_spacing = lp["line_spacing_side"] if side in ("left", "right") else lp["line_spacing_topbot"]
    bx, by = band["band_x"], band["band_y"]
    bw, bh = band["band_w"], band["band_h"]

    # Measure total text block height.
    line_heights = []
    for text, font, _ in lines:
        bbox = draw.textbbox((0, 0), text, font=font)
        line_heights.append(bbox[3] - bbox[1])
    total_h = sum(line_heights) + line_spacing * (len(lines) - 1)

    if side in ("left", "right"):
        # Left-aligned with padding, vertically centered in band.
        tx = bx + lp["band_padding_x"]
        ty = by + (bh - total_h) // 2
        for i, (text, font, color) in enumerate(lines):
            draw.text((tx, ty), text, fill=color, font=font)
            ty += line_heights[i] + line_spacing
    else:
        # Horizontally centered in band, vertically centered.
        ty = by + (bh - total_h) // 2
        for i, (text, font, color) in enumerate(lines):
            bbox_rect = draw.textbbox((0, 0), text, font=font)
            tw = bbox_rect[2] - bbox_rect[0]
            tx = bx + (bw - tw) // 2
            draw.text((tx, ty), text, fill=color, font=font)
            ty += line_heights[i] + line_spacing


# ── Full composite (video + annotation) ──────────────────────────


def render_annotated_clip(
    clip_config: dict,
    bbox_w: int,
    bbox_h: int,
    bg_color: tuple[int, int, int],
    colors: dict[str, tuple[int, int, int]],
    fps: int,
) -> CompositeVideoClip:
    """Render a complete AnnotatedClip: video + flush annotation band.

    Loads the video clip, computes the unit-centered layout (video + band
    as one tight rectangle centered in the bbox), then composites.

    Args:
        clip_config: Dict with path, annotation_side, annotations.
        bbox_w, bbox_h: Bounding box for the entire atom.
        bg_color: Section background RGB.
        colors: Color palette.
        fps: Target frame rate.

    Returns:
        CompositeVideoClip at (bbox_w, bbox_h) size.
    """
    annotations = clip_config.get("annotations", [])

    # Load video first — we need source dimensions for layout.
    video = load_clip(clip_config["path"], fps)
    duration = video.duration
    src_w, src_h = video.size

    # No annotations → just the video centered in the bbox, no band.
    if not annotations:
        scale = min(bbox_w / src_w, bbox_h / src_h)
        new_w = int(src_w * scale)
        new_h = int(src_h * scale)
        video = video.resized((new_w, new_h))
        cx = (bbox_w - new_w) // 2
        cy = (bbox_h - new_h) // 2
        video = video.with_position((cx, cy))

        bg_frame = np.full((bbox_h, bbox_w, 3), bg_color, dtype=np.uint8)
        bg_clip = ImageClip(bg_frame).with_duration(duration).with_position((0, 0))

        no_annot_clip = CompositeVideoClip(
            [bg_clip, video], size=(bbox_w, bbox_h),
        ).with_fps(fps)

        # Apply per-clip overlays if present.
        overlay_items = clip_config.get("overlay")
        if overlay_items:
            overlay_font_size = max(10, round(20 * bbox_h / 900))
            overlay_region = (cx, cy, new_w, new_h)

            def _apply_overlay(get_frame, t):
                return apply_overlays_to_frame(
                    get_frame(t), overlay_items, colors, overlay_font_size,
                    region=overlay_region,
                )

            no_annot_clip = no_annot_clip.transform(_apply_overlay)

        return no_annot_clip

    # Has annotations → full unit layout with band + border.
    side = clip_config["annotation_side"]

    band = compute_annotation_band(
        side, annotations, bbox_w, bbox_h, colors, src_w, src_h,
    )
    lp = band["lp"]

    # Render the static annotation background frame.
    annot_frame = render_annotated_clip_frame(
        bbox_w, bbox_h, side, annotations, bg_color, colors, src_w, src_h,
    )

    # Inset the video from the unit boundary so the border stays visible.
    # The band-adjacent edge needs no inset (border is on the same layer).
    b = lp["border_width"]
    if side == "left":
        inset_x, inset_y = 0, b
        inset_w = band["clip_w"] - b
        inset_h = band["clip_h"] - 2 * b
    elif side == "right":
        inset_x, inset_y = b, b
        inset_w = band["clip_w"] - b
        inset_h = band["clip_h"] - 2 * b
    elif side == "above":
        inset_x, inset_y = b, 0
        inset_w = band["clip_w"] - 2 * b
        inset_h = band["clip_h"] - b
    else:  # below
        inset_x, inset_y = b, b
        inset_w = band["clip_w"] - 2 * b
        inset_h = band["clip_h"] - b

    # Scale video to fit inset area, preserving aspect ratio.
    scale = min(inset_w / src_w, inset_h / src_h)
    new_w = int(src_w * scale)
    new_h = int(src_h * scale)
    video = video.resized((new_w, new_h))

    # Center within the inset area.
    cx = band["clip_x"] + inset_x + (inset_w - new_w) // 2
    cy = band["clip_y"] + inset_y + (inset_h - new_h) // 2

    # Annotation layer: static frame for the full duration.
    annot_clip = (
        ImageClip(annot_frame)
        .with_duration(duration)
        .with_position((0, 0))
    )

    # Video layer: inset from border so border stays visible.
    video = video.with_position((cx, cy))

    # Composite: annotation background (behind) + video (on top).
    composite = CompositeVideoClip(
        [annot_clip, video],
        size=(bbox_w, bbox_h),
    ).with_fps(fps)

    # Apply per-clip overlays if present.
    overlay_items = clip_config.get("overlay")
    if overlay_items:
        overlay_font_size = max(10, round(20 * bbox_h / 900))
        overlay_region = (
            band["unit_x"], band["unit_y"],
            band["unit_w"], band["unit_h"],
        )

        def _apply_overlay(get_frame, t):
            return apply_overlays_to_frame(
                get_frame(t), overlay_items, colors, overlay_font_size,
                region=overlay_region,
            )

        composite = composite.transform(_apply_overlay)

    return composite
