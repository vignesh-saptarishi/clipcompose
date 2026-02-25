"""Section renderers for v3 compositor.

A section is the top-level unit in a manifest: header + content.
Each template type has its own section renderer. Currently only
single_clip is implemented.

Section layout (single_clip):
  ┌─────────────────────────────────────┐
  │  ┌───────────────────────────────┐  │  ← outer padding
  │  │ ■ Section Header              │  │  ← accent bar + title
  │  │   Subtitle text               │  │  ← subtitle (muted)
  │  └───────────────────────────────┘  │
  │                                      │
  │  ┌──────────┬────────────────────┐  │
  │  │ CRASHED  │                    │  │
  │  │ g=-15.0  │    video clip      │  │  ← AnnotatedClip atom
  │  │ ac=0.95  │                    │  │
  │  └──────────┴────────────────────┘  │
  │                                      │  ← outer padding
  └─────────────────────────────────────┘
"""

import numpy as np
from PIL import Image, ImageDraw
from moviepy import ImageClip, CompositeVideoClip, vfx

from .common import load_font
from .atoms import render_annotated_clip


# ── Scaling system ────────────────────────────────────────────────
#
# Section-level constants scale with the output resolution height,
# just like atom-level constants scale with bbox_h. Reference is
# 1080p (h=1080). Each constant is (value_at_1080, floor).

_SEC_REF_H = 1080

_REF_OUTER_PADDING = (24, 6)
_REF_TITLE_BAR_H = (50, 16)
_REF_SUBTITLE_GAP = (6, 2)
_REF_TITLE_FONT_SIZE = (30, 10)
_REF_SUBTITLE_FONT_SIZE = (24, 9)
_REF_SUBTITLE_BOTTOM_PAD = (8, 3)
_REF_HEADER_CONTENT_GAP = (16, 4)
_REF_GRID_GAP = (12, 4)
_REF_GROUP_GAP = (36, 10)   # gap between left/right groups in paired_2x2

_REF_COL_HEADER_FONT_SIZE = (22, 8)
_REF_COL_HEADER_GAP = (18, 5)

_REF_TITLE_CARD_TITLE_FONT = (64, 20)
_REF_TITLE_CARD_SUBTITLE_FONT = (36, 12)
_REF_TITLE_CARD_GAP = (30, 10)
_REF_TITLE_CARD_ACCENT_BAR_H = (4, 2)     # thin bar at top edge
_REF_TITLE_CARD_UNDERLINE_H = (3, 1)      # underline below title
_REF_TITLE_CARD_UNDERLINE_GAP = (12, 4)   # gap between title and underline
_REF_TITLE_CARD_UNDERLINE_FRAC = 0.6      # underline width as fraction of frame

# text_slide scaling references.
_REF_TEXT_SLIDE_FONT_SIZE = (28, 10)       # base font size for text lines
_REF_TEXT_SLIDE_BOLD_BUMP = (4, 2)         # extra size for bold lines
_REF_TEXT_SLIDE_LINE_SPACING = (16, 5)     # vertical space between lines
_REF_TEXT_SLIDE_COL_PADDING = (40, 10)     # horizontal padding inside each column
_REF_TEXT_SLIDE_DIVIDER_W = (2, 1)         # divider line width
_REF_TEXT_SLIDE_3COL_FONT_SCALE = 0.85     # font reduction for 3 columns


def _sec_scale(ref_and_floor: tuple[int, int], h: int) -> int:
    """Scale a reference pixel value to the current output height."""
    ref_val, floor = ref_and_floor
    return max(floor, round(ref_val * h / _SEC_REF_H))


def _section_layout(h: int) -> dict[str, int]:
    """Compute all scaled section layout params for output height h."""
    return {
        "outer_padding": _sec_scale(_REF_OUTER_PADDING, h),
        "title_bar_h": _sec_scale(_REF_TITLE_BAR_H, h),
        "subtitle_gap": _sec_scale(_REF_SUBTITLE_GAP, h),
        "title_font_size": _sec_scale(_REF_TITLE_FONT_SIZE, h),
        "subtitle_font_size": _sec_scale(_REF_SUBTITLE_FONT_SIZE, h),
        "subtitle_bottom_pad": _sec_scale(_REF_SUBTITLE_BOTTOM_PAD, h),
        "header_content_gap": _sec_scale(_REF_HEADER_CONTENT_GAP, h),
        "grid_gap": _sec_scale(_REF_GRID_GAP, h),
    }


# ── Header rendering ─────────────────────────────────────────────


def render_section_header_frame(
    title: str,
    resolution: tuple[int, int],
    bg_color: tuple[int, int, int],
    colors: dict[str, tuple[int, int, int]],
    subtitle: str | None = None,
) -> np.ndarray:
    """Render a section header as a numpy frame.

    The header is a full-width accent-colored bar with centered title text.
    If a subtitle is provided, it appears below the bar in muted text on
    the dark background. All sizes scale with the output resolution height.

    Args:
        title: Section title text.
        resolution: (width, height) of the full output frame.
        bg_color: Section background RGB.
        colors: Palette — uses "accent" and "text".
        subtitle: Optional subtitle text.

    Returns:
        numpy array of shape (header_h, width, 3). Header height varies
        based on whether subtitle is present.
    """
    w, h = resolution
    sl = _section_layout(h)
    accent = colors["accent"]
    text_color = colors["text"]

    title_bar_h = sl["title_bar_h"]
    title_font_size = sl["title_font_size"]
    subtitle_font_size = sl["subtitle_font_size"]
    subtitle_gap = sl["subtitle_gap"]

    # Compute total header height.
    header_h = title_bar_h
    if subtitle:
        sub_font = load_font(subtitle_font_size)
        draw_tmp = ImageDraw.Draw(Image.new("RGB", (1, 1)))
        sub_bbox = draw_tmp.textbbox((0, 0), subtitle, font=sub_font)
        sub_h = sub_bbox[3] - sub_bbox[1]
        header_h = title_bar_h + subtitle_gap + sub_h + sl["subtitle_bottom_pad"]

    img = Image.new("RGB", (w, header_h), bg_color)
    draw = ImageDraw.Draw(img)

    # Accent bar.
    draw.rectangle([(0, 0), (w, title_bar_h)], fill=accent)

    # Title text, centered in the accent bar.
    title_font = load_font(title_font_size)
    title_bbox = draw.textbbox((0, 0), title, font=title_font)
    tw = title_bbox[2] - title_bbox[0]
    th = title_bbox[3] - title_bbox[1]
    tx = (w - tw) // 2
    ty = (title_bar_h - th) // 2
    draw.text((tx, ty), title, fill=text_color, font=title_font)

    # Subtitle below the bar.
    if subtitle:
        sub_font = load_font(subtitle_font_size)
        sub_color = colors.get("text_secondary", (170, 170, 168))
        sub_bbox = draw.textbbox((0, 0), subtitle, font=sub_font)
        sw = sub_bbox[2] - sub_bbox[0]
        sx = (w - sw) // 2
        sy = title_bar_h + subtitle_gap
        draw.text((sx, sy), subtitle, fill=sub_color, font=sub_font)

    return np.array(img)


# ── Title card renderer ──────────────────────────────────────────


def render_title_card(
    config: dict,
    video_settings: dict,
    colors: dict[str, tuple[int, int, int]],
) -> ImageClip:
    """Render a title_card section: centered text on dark background.

    Full-frame static card with large title and optional smaller subtitle.
    No header bar, no video clips. Duration from config.

    Args:
        config: Section config with title, duration, optional subtitle.
        video_settings: Dict with resolution, fps, background.
        colors: Parsed color palette (uses "text" and "text_secondary").

    Returns:
        ImageClip at the full output resolution with specified duration.
    """
    resolution = video_settings["resolution"]
    bg_color = video_settings["background"]
    w, h = resolution

    title_text = config["title"]
    subtitle_text = config.get("subtitle")
    duration = config["duration"]

    # Scale all layout values to the output resolution.
    title_font_size = _sec_scale(_REF_TITLE_CARD_TITLE_FONT, h)
    subtitle_font_size = _sec_scale(_REF_TITLE_CARD_SUBTITLE_FONT, h)
    accent_bar_h = _sec_scale(_REF_TITLE_CARD_ACCENT_BAR_H, h)
    underline_h = _sec_scale(_REF_TITLE_CARD_UNDERLINE_H, h)
    underline_gap = _sec_scale(_REF_TITLE_CARD_UNDERLINE_GAP, h)

    title_color = colors.get("text", (213, 213, 211))
    subtitle_color = colors.get("text_secondary", (136, 136, 136))
    accent = colors.get("accent", (177, 19, 77))

    img = Image.new("RGB", (w, h), bg_color)
    draw = ImageDraw.Draw(img)

    title_font = load_font(title_font_size)
    subtitle_font = load_font(subtitle_font_size)

    # Measure title block (supports \n line breaks).
    title_bbox = draw.multiline_textbbox((0, 0), title_text, font=title_font)
    title_tw = title_bbox[2] - title_bbox[0]
    title_th = title_bbox[3] - title_bbox[1]

    # Measure subtitle if present.
    sub_th = 0
    sub_tw = 0
    if subtitle_text:
        sub_bbox = draw.multiline_textbbox((0, 0), subtitle_text, font=subtitle_font)
        sub_tw = sub_bbox[2] - sub_bbox[0]
        sub_th = sub_bbox[3] - sub_bbox[1]

    # Total block height: title + underline_gap + underline + (underline_gap + subtitle).
    total_h = title_th + underline_gap + underline_h
    if subtitle_text:
        total_h += underline_gap + sub_th

    # Draw accent bar at the very top edge of the frame.
    draw.rectangle([(0, 0), (w, accent_bar_h)], fill=accent)

    # Center the text block vertically in the space below the accent bar.
    block_y = accent_bar_h + (h - accent_bar_h - total_h) // 2

    # Draw title — horizontally centered.
    title_x = (w - title_tw) // 2
    draw.multiline_text(
        (title_x, block_y), title_text,
        fill=title_color, font=title_font, align="center",
    )

    # Draw accent underline below the title text, centered horizontally.
    underline_w = int(w * _REF_TITLE_CARD_UNDERLINE_FRAC)
    underline_x = (w - underline_w) // 2
    underline_y = block_y + title_th + underline_gap
    draw.rectangle(
        [(underline_x, underline_y), (underline_x + underline_w, underline_y + underline_h)],
        fill=accent,
    )

    # Draw subtitle below the underline.
    if subtitle_text:
        sub_x = (w - sub_tw) // 2
        sub_y = underline_y + underline_h + underline_gap
        draw.multiline_text(
            (sub_x, sub_y), subtitle_text,
            fill=subtitle_color, font=subtitle_font, align="center",
        )

    frame = np.array(img)
    clip = ImageClip(frame).with_duration(duration).with_fps(video_settings["fps"])
    return clip


# ── Text slide renderer ──────────────────────────────────────────


def render_text_slide(
    config: dict,
    video_settings: dict,
    colors: dict[str, tuple[int, int, int]],
) -> ImageClip:
    """Render a text_slide section: header + 1-3 columns of styled text lines.

    Uses the standard section container (header bar + subtitle). Columns are
    equal width with accent-colored vertical dividers between them. Text is
    vertically centered within each column, left-aligned with padding.
    For 3 columns, font size is reduced to maximize text density.

    Args:
        config: Section config with header, duration, columns list.
        video_settings: Dict with resolution, fps, background.
        colors: Parsed color palette.

    Returns:
        ImageClip at the full output resolution with specified duration.
    """
    resolution = video_settings["resolution"]
    fps = video_settings["fps"]
    bg_color = video_settings["background"]
    w, h = resolution
    sl = _section_layout(h)
    duration = config["duration"]
    columns = config["columns"]
    n_cols = len(columns)

    # Render the section header.
    header_frame = render_section_header_frame(
        title=config["header"],
        resolution=resolution,
        bg_color=bg_color,
        colors=colors,
        subtitle=config.get("subtitle"),
    )
    header_h = header_frame.shape[0]

    # Content area: below header, inside outer padding.
    outer_pad = sl["outer_padding"]
    content_x = outer_pad
    content_y = header_h + sl["header_content_gap"]
    content_w = w - 2 * outer_pad
    content_h = h - content_y - outer_pad

    # Font sizing — reduce for 3 columns to maximize text density.
    base_font_size = _sec_scale(_REF_TEXT_SLIDE_FONT_SIZE, h)
    bold_bump = _sec_scale(_REF_TEXT_SLIDE_BOLD_BUMP, h)
    if n_cols >= 3:
        base_font_size = max(10, int(base_font_size * _REF_TEXT_SLIDE_3COL_FONT_SCALE))
        bold_bump = max(1, int(bold_bump * _REF_TEXT_SLIDE_3COL_FONT_SCALE))

    line_spacing = _sec_scale(_REF_TEXT_SLIDE_LINE_SPACING, h)
    col_padding = _sec_scale(_REF_TEXT_SLIDE_COL_PADDING, h)
    divider_w = _sec_scale(_REF_TEXT_SLIDE_DIVIDER_W, h)

    # Column widths — equal division with divider gaps.
    if n_cols == 1:
        col_w = content_w
    else:
        total_divider_w = (n_cols - 1) * divider_w
        col_w = (content_w - total_divider_w) // n_cols

    # Build the full frame: header on top of bg, then draw text + dividers.
    img = Image.new("RGB", (w, h), bg_color)
    # Paste header.
    header_img = Image.fromarray(header_frame)
    img.paste(header_img, (0, 0))
    draw = ImageDraw.Draw(img)

    # Muted accent color for dividers — blend accent toward bg.
    accent = colors.get("accent", (177, 19, 77))
    divider_color = tuple(
        (a + b) // 2 for a, b in zip(accent, bg_color)
    )

    # Draw each column's text lines.
    from .common import resolve_color
    default_color = colors.get("text_secondary", (136, 136, 136))

    for c_idx, col in enumerate(columns):
        col_x = content_x + c_idx * (col_w + divider_w)
        lines = col["lines"]

        # Build (text, font, color) tuples for this column.
        rendered_lines = []
        for line in lines:
            weight = line.get("weight", "normal")
            fs = base_font_size + bold_bump if weight == "bold" else base_font_size
            font = load_font(fs)
            color_ref = line.get("color")
            if color_ref:
                text_color = resolve_color(color_ref, colors)
            else:
                text_color = default_color
            rendered_lines.append((line["text"], font, text_color))

        # Measure total text block height for vertical centering.
        line_heights = []
        for text, font, _ in rendered_lines:
            bbox = draw.textbbox((0, 0), text, font=font)
            line_heights.append(bbox[3] - bbox[1])
        total_text_h = sum(line_heights)
        if rendered_lines:
            total_text_h += line_spacing * (len(rendered_lines) - 1)

        # Vertically center text block within content area.
        text_y = content_y + (content_h - total_text_h) // 2
        align = col.get("align", "left")

        for i, (text, font, color) in enumerate(rendered_lines):
            if align == "center":
                # Center each line within the column.
                line_bbox = draw.textbbox((0, 0), text, font=font)
                line_w = line_bbox[2] - line_bbox[0]
                text_x = col_x + (col_w - line_w) // 2
            else:
                text_x = col_x + col_padding
            draw.text((text_x, text_y), text, fill=color, font=font)
            text_y += line_heights[i] + line_spacing

    # Draw dividers between columns.
    if n_cols > 1:
        for d_idx in range(n_cols - 1):
            div_x = content_x + (d_idx + 1) * col_w + d_idx * divider_w + divider_w // 2
            div_top = content_y
            div_bottom = content_y + content_h
            draw.line(
                [(div_x, div_top), (div_x, div_bottom)],
                fill=divider_color, width=divider_w,
            )

    frame = np.array(img)
    clip = ImageClip(frame).with_duration(duration).with_fps(fps)
    return clip


# ── Section renderer ──────────────────────────────────────────────


def render_single_clip(
    config: dict,
    video_settings: dict,
    colors: dict[str, tuple[int, int, int]],
) -> CompositeVideoClip:
    """Render a single_clip section: header + one AnnotatedClip.

    Layout:
      1. Full-width header bar (accent + title + optional subtitle).
      2. AnnotatedClip atom centered in the remaining content area.
      3. Outer padding on all sides.

    Args:
        config: Section config dict with header, subtitle, clip.
        video_settings: Dict with resolution, fps, background.
        colors: Parsed color palette.

    Returns:
        CompositeVideoClip at the full output resolution. No fade effects
        (transitions are assembly-only).
    """
    resolution = video_settings["resolution"]
    fps = video_settings["fps"]
    bg_color = video_settings["background"]
    w, h = resolution
    sl = _section_layout(h)

    # Render the section header.
    header_frame = render_section_header_frame(
        title=config["header"],
        resolution=resolution,
        bg_color=bg_color,
        colors=colors,
        subtitle=config.get("subtitle"),
    )
    header_h = header_frame.shape[0]

    # Content area: everything below header, inside outer padding.
    outer_pad = sl["outer_padding"]
    content_x = outer_pad
    content_y = header_h + sl["header_content_gap"]
    content_w = w - 2 * outer_pad
    content_h = h - content_y - outer_pad

    # Render the AnnotatedClip atom.
    atom = render_annotated_clip(
        clip_config=config["clip"],
        bbox_w=content_w,
        bbox_h=content_h,
        bg_color=bg_color,
        colors=colors,
        fps=fps,
    )
    duration = atom.duration

    # Background layer.
    bg_frame = np.full((h, w, 3), bg_color, dtype=np.uint8)
    bg_clip = ImageClip(bg_frame).with_duration(duration)

    # Header layer.
    header_clip = (
        ImageClip(header_frame)
        .with_duration(duration)
        .with_position((0, 0))
    )

    # Atom layer — positioned in the content area.
    atom = atom.with_position((content_x, content_y))

    # Composite all layers.
    section = (
        CompositeVideoClip([bg_clip, header_clip, atom], size=(w, h))
        .with_fps(fps)
    )

    return section


# ── Grid renderers ───────────────────────────────────────────────


def render_grid_2x1(
    config: dict,
    video_settings: dict,
    colors: dict[str, tuple[int, int, int]],
) -> CompositeVideoClip:
    """Render a grid_2x1 section: header + two clips side by side."""
    return _render_grid(config, video_settings, colors, cols=2, rows=1)


def render_grid_2x2(
    config: dict,
    video_settings: dict,
    colors: dict[str, tuple[int, int, int]],
) -> CompositeVideoClip:
    """Render a grid_2x2 section: header + four clips in a 2x2 grid."""
    return _render_grid(config, video_settings, colors, cols=2, rows=2)


def render_grid_3x1(
    config: dict,
    video_settings: dict,
    colors: dict[str, tuple[int, int, int]],
) -> CompositeVideoClip:
    """Render a grid_3x1 section: header + three clips side by side."""
    return _render_grid(config, video_settings, colors, cols=3, rows=1)


def render_grid_2x4(
    config: dict,
    video_settings: dict,
    colors: dict[str, tuple[int, int, int]],
) -> CompositeVideoClip:
    """Render a grid_2x4 section: header + eight clips in 2 cols x 4 rows."""
    return _render_grid(config, video_settings, colors, cols=2, rows=4)


def render_grid_3x4(
    config: dict,
    video_settings: dict,
    colors: dict[str, tuple[int, int, int]],
) -> CompositeVideoClip:
    """Render a grid_3x4 section: header + twelve clips in 3 cols x 4 rows."""
    return _render_grid(config, video_settings, colors, cols=3, rows=4)


def _render_grid(
    config: dict,
    video_settings: dict,
    colors: dict[str, tuple[int, int, int]],
    cols: int,
    rows: int,
) -> CompositeVideoClip:
    """Shared grid renderer — divide content area into cells, one atom per cell.

    Layout:
      1. Full-width header bar (same as single_clip).
      2. Content area divided into cols x rows equal cells with gap.
      3. Each cell gets one AnnotatedClip atom.
      4. Duration = shortest clip (all atoms trimmed to match).
    """
    resolution = video_settings["resolution"]
    fps = video_settings["fps"]
    bg_color = video_settings["background"]
    w, h = resolution
    sl = _section_layout(h)

    # Render the section header (shared with single_clip).
    header_frame = render_section_header_frame(
        title=config["header"],
        resolution=resolution,
        bg_color=bg_color,
        colors=colors,
        subtitle=config.get("subtitle"),
    )
    header_h = header_frame.shape[0]

    # Content area: everything below header, inside outer padding.
    outer_pad = sl["outer_padding"]
    gap = sl["grid_gap"]
    content_x = outer_pad
    content_y = header_h + sl["header_content_gap"]
    content_w = w - 2 * outer_pad
    content_h = h - content_y - outer_pad

    # Optional column headers — measure and reserve vertical space.
    column_headers = config.get("column_headers")
    col_header_h = 0
    if column_headers:
        col_hdr_font_size = _sec_scale(_REF_COL_HEADER_FONT_SIZE, h)
        col_hdr_gap = _sec_scale(_REF_COL_HEADER_GAP, h)
        col_hdr_font = load_font(col_hdr_font_size)
        draw_tmp = ImageDraw.Draw(Image.new("RGB", (1, 1)))
        max_th = 0
        for text in column_headers:
            bbox = draw_tmp.textbbox((0, 0), text, font=col_hdr_font)
            max_th = max(max_th, bbox[3] - bbox[1])
        col_header_h = max_th + col_hdr_gap
        content_h -= col_header_h

    # Cell dimensions: divide content area evenly with gaps.
    cell_w = (content_w - (cols - 1) * gap) // cols
    cell_h = (content_h - (rows - 1) * gap) // rows

    # Single-row grids: cap cell_h to reduce dead space. Videos are
    # typically landscape (~1.5:1), so cells taller than ~0.75 * cell_w
    # just add empty space above/below the video+annotation unit.
    if rows == 1:
        cell_h = min(cell_h, int(cell_w * 0.75))

    # Render each clip as an atom in its cell.
    clips = config["clips"]
    atoms = []
    for clip_config in clips:
        atom = render_annotated_clip(
            clip_config=clip_config,
            bbox_w=cell_w,
            bbox_h=cell_h,
            bg_color=bg_color,
            colors=colors,
            fps=fps,
        )
        atoms.append(atom)

    # Duration = longest clip. Shorter clips get their last frame frozen.
    duration = max(a.duration for a in atoms)

    # Center column headers + grid as one unit in the full content area.
    # full_content_h is the original content area before col_header_h was
    # subtracted; content_h is what remained for grid cells.
    full_content_h = content_h + col_header_h
    total_grid_h = rows * cell_h + (rows - 1) * gap
    total_unit_h = col_header_h + total_grid_h
    y_offset = (full_content_h - total_unit_h) // 2

    # Absolute y positions for column headers and grid first row.
    unit_top_y = content_y + y_offset
    grid_top_y = unit_top_y + col_header_h

    # Background layer — draw column headers flush above the grid.
    bg_img = Image.new("RGB", (w, h), bg_color)
    if column_headers:
        draw = ImageDraw.Draw(bg_img)
        col_hdr_color = colors.get("text_secondary", (170, 170, 168))
        col_hdr_font = load_font(_sec_scale(_REF_COL_HEADER_FONT_SIZE, h))
        for col_idx, text in enumerate(column_headers):
            col_x = content_x + col_idx * (cell_w + gap)
            bbox = draw.textbbox((0, 0), text, font=col_hdr_font)
            tw = bbox[2] - bbox[0]
            tx = col_x + (cell_w - tw) // 2
            ty = unit_top_y
            draw.text((tx, ty), text, fill=col_hdr_color, font=col_hdr_font)
    bg_frame = np.array(bg_img)
    bg_clip = ImageClip(bg_frame).with_duration(duration)

    # Header layer.
    header_clip = (
        ImageClip(header_frame)
        .with_duration(duration)
        .with_position((0, 0))
    )

    # Position each atom in its grid cell. Freeze shorter clips at last frame.
    layers = [bg_clip, header_clip]
    for idx, atom in enumerate(atoms):
        col = idx % cols
        row = idx // cols
        x = content_x + col * (cell_w + gap)
        y = grid_top_y + row * (cell_h + gap)
        if atom.duration < duration:
            atom = atom.with_effects(
                [vfx.Freeze(t="end", total_duration=duration)]
            )
        atom = atom.with_position((x, y))
        layers.append(atom)

    section = (
        CompositeVideoClip(layers, size=(w, h))
        .with_fps(fps)
    )
    return section


# ── Paired group renderers ───────────────────────────────────


def render_paired_2x2(
    config: dict,
    video_settings: dict,
    colors: dict[str, tuple[int, int, int]],
) -> CompositeVideoClip:
    """Render a paired_2x2 section: two side-by-side groups, each a 2x2 grid.

    Layout:
      1. Full-width section header bar (same as other templates).
      2. Two groups side by side, separated by group_gap.
      3. Each group has: centered header text + 2x2 grid of annotated clips.
      4. Duration = longest clip across both groups. Shorter clips freeze-frame.
    """
    resolution = video_settings["resolution"]
    fps = video_settings["fps"]
    bg_color = video_settings["background"]
    w, h = resolution
    sl = _section_layout(h)

    # Section header (shared with all templates).
    header_frame = render_section_header_frame(
        title=config["header"],
        resolution=resolution,
        bg_color=bg_color,
        colors=colors,
        subtitle=config.get("subtitle"),
    )
    header_h = header_frame.shape[0]

    # Content area: below header, inside outer padding.
    outer_pad = sl["outer_padding"]
    gap = sl["grid_gap"]
    group_gap = _sec_scale(_REF_GROUP_GAP, h)
    content_x = outer_pad
    content_y = header_h + sl["header_content_gap"]
    content_w = w - 2 * outer_pad
    content_h = h - content_y - outer_pad

    # Group header measurement (same font as column_headers).
    grp_hdr_font_size = _sec_scale(_REF_COL_HEADER_FONT_SIZE, h)
    grp_hdr_gap = _sec_scale(_REF_COL_HEADER_GAP, h)
    grp_hdr_font = load_font(grp_hdr_font_size)
    draw_tmp = ImageDraw.Draw(Image.new("RGB", (1, 1)))

    max_hdr_h = 0
    for group in config["groups"]:
        bbox = draw_tmp.textbbox((0, 0), group["header"], font=grp_hdr_font)
        max_hdr_h = max(max_hdr_h, bbox[3] - bbox[1])
    grp_header_h = max_hdr_h + grp_hdr_gap

    # Available height for the 2x2 grid within each group.
    grid_content_h = content_h - grp_header_h

    # Group width: split content area in two with group_gap between.
    group_w = (content_w - group_gap) // 2

    # Cell dimensions: 2 cols x 2 rows within each group.
    cell_w = (group_w - gap) // 2
    cell_h = (grid_content_h - gap) // 2

    # Render all 8 atoms (4 per group).
    groups = config["groups"]
    all_atoms = []
    for group in groups:
        group_atoms = []
        for clip_config in group["clips"]:
            atom = render_annotated_clip(
                clip_config=clip_config,
                bbox_w=cell_w,
                bbox_h=cell_h,
                bg_color=bg_color,
                colors=colors,
                fps=fps,
            )
            group_atoms.append(atom)
        all_atoms.append(group_atoms)

    # Duration = longest clip across both groups.
    duration = max(
        a.duration for group_atoms in all_atoms for a in group_atoms
    )

    # Vertical centering: center grp_header + grid as one unit.
    total_grid_h = 2 * cell_h + gap
    total_unit_h = grp_header_h + total_grid_h
    y_offset = (content_h - total_unit_h) // 2
    unit_top_y = content_y + y_offset
    grid_top_y = unit_top_y + grp_header_h

    # Background layer with group headers.
    bg_img = Image.new("RGB", (w, h), bg_color)
    draw = ImageDraw.Draw(bg_img)
    grp_hdr_color = colors.get("text_secondary", (170, 170, 168))

    for g_idx, group in enumerate(groups):
        gx = content_x + g_idx * (group_w + group_gap)
        # Center header text over the group width.
        bbox = draw.textbbox((0, 0), group["header"], font=grp_hdr_font)
        tw = bbox[2] - bbox[0]
        tx = gx + (group_w - tw) // 2
        ty = unit_top_y
        draw.text((tx, ty), group["header"], fill=grp_hdr_color, font=grp_hdr_font)

    # Vertical divider between the two groups — thin line centered in group_gap.
    divider_x = content_x + group_w + group_gap // 2
    divider_top = unit_top_y
    divider_bottom = grid_top_y + total_grid_h
    divider_color = colors.get("text_secondary", (170, 170, 168))
    draw.line(
        [(divider_x, divider_top), (divider_x, divider_bottom)],
        fill=divider_color, width=1,
    )

    bg_frame = np.array(bg_img)
    bg_clip = ImageClip(bg_frame).with_duration(duration)

    # Section header layer.
    header_clip = (
        ImageClip(header_frame)
        .with_duration(duration)
        .with_position((0, 0))
    )

    # Position each atom in its group's 2x2 grid.
    layers = [bg_clip, header_clip]
    for g_idx, group_atoms in enumerate(all_atoms):
        gx = content_x + g_idx * (group_w + group_gap)
        for c_idx, atom in enumerate(group_atoms):
            col = c_idx % 2
            row = c_idx // 2
            x = gx + col * (cell_w + gap)
            y = grid_top_y + row * (cell_h + gap)
            if atom.duration < duration:
                atom = atom.with_effects(
                    [vfx.Freeze(t="end", total_duration=duration)]
                )
            atom = atom.with_position((x, y))
            layers.append(atom)

    section = (
        CompositeVideoClip(layers, size=(w, h))
        .with_fps(fps)
    )
    return section
