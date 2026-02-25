"""Tests for clipcompose section renderer.

Tests the header rendering and the section composition (header + atom).
Uses mock clip configs that don't require real video files — the atom
renderer is tested separately.
"""

import numpy as np
import pytest
from PIL import Image

from clipcompose.sections import (
    render_section_header_frame,
    _section_layout,
    _sec_scale,
    _REF_COL_HEADER_FONT_SIZE,
    _REF_TITLE_CARD_TITLE_FONT,
    _REF_TITLE_CARD_SUBTITLE_FONT,
    _REF_GROUP_GAP,
    _REF_TEXT_SLIDE_FONT_SIZE,
    _REF_TEXT_SLIDE_DIVIDER_W,
)


TEST_COLORS = {
    "text": (213, 213, 211),
    "text_secondary": (136, 136, 136),
    "accent": (177, 19, 77),
    "landed": (80, 220, 120),
    "crashed": (240, 70, 70),
}

TEST_BG = (26, 26, 26)
TEST_RESOLUTION = (1920, 1080)


class TestRenderSectionHeaderFrame:
    def test_returns_correct_width(self):
        frame = render_section_header_frame(
            title="Test Header",
            resolution=TEST_RESOLUTION,
            bg_color=TEST_BG,
            colors=TEST_COLORS,
        )
        assert frame.shape[1] == 1920
        assert frame.shape[2] == 3
        assert frame.dtype == np.uint8

    def test_height_without_subtitle(self):
        frame = render_section_header_frame(
            title="Test Header",
            resolution=TEST_RESOLUTION,
            bg_color=TEST_BG,
            colors=TEST_COLORS,
        )
        # Should be a reasonable header height (50-70px range).
        assert 40 <= frame.shape[0] <= 80

    def test_height_with_subtitle_is_taller(self):
        frame_no_sub = render_section_header_frame(
            title="Test", resolution=TEST_RESOLUTION,
            bg_color=TEST_BG, colors=TEST_COLORS,
        )
        frame_sub = render_section_header_frame(
            title="Test", subtitle="A subtitle",
            resolution=TEST_RESOLUTION,
            bg_color=TEST_BG, colors=TEST_COLORS,
        )
        assert frame_sub.shape[0] > frame_no_sub.shape[0]

    def test_accent_bar_pixels(self):
        """The top rows should contain accent color pixels (the title bar)."""
        frame = render_section_header_frame(
            title="Test", resolution=TEST_RESOLUTION,
            bg_color=TEST_BG, colors=TEST_COLORS,
        )
        # Sample a pixel in the top-left of the accent bar area.
        top_pixel = tuple(frame[5, 100, :])
        # Should be the accent color (or close to it).
        assert top_pixel == TEST_COLORS["accent"]


class TestGridLayout:
    """Test grid cell dimension math using _section_layout."""

    def test_2x1_cells_fit_in_content_area(self):
        """Two cells + gap should not exceed content width."""
        h = 1080
        sl = _section_layout(h)
        content_w = 1920 - 2 * sl["outer_padding"]
        gap = sl["grid_gap"]
        cell_w = (content_w - gap) // 2
        assert 2 * cell_w + gap <= content_w

    def test_2x2_cells_fit_in_content_area(self):
        """Four cells + gaps should not exceed content area."""
        h = 1080
        sl = _section_layout(h)
        content_w = 1920 - 2 * sl["outer_padding"]
        gap = sl["grid_gap"]
        cell_w = (content_w - gap) // 2
        assert 2 * cell_w + gap <= content_w

        # Vertical: need header height for content_h calc.
        header_frame = render_section_header_frame(
            title="Test", resolution=(1920, 1080),
            bg_color=TEST_BG, colors=TEST_COLORS,
        )
        header_h = header_frame.shape[0]
        content_h = h - header_h - sl["header_content_gap"] - sl["outer_padding"]
        cell_h = (content_h - gap) // 2
        assert 2 * cell_h + gap <= content_h

    def test_grid_gap_scales_with_resolution(self):
        """Gap should be smaller at lower resolutions."""
        sl_1080 = _section_layout(1080)
        sl_540 = _section_layout(540)
        sl_270 = _section_layout(270)
        assert sl_1080["grid_gap"] > sl_540["grid_gap"]
        assert sl_540["grid_gap"] >= sl_270["grid_gap"]

    def test_3x1_cells_fit_in_content_area(self):
        """Three cells + 2 gaps should not exceed content width."""
        h = 1080
        sl = _section_layout(h)
        content_w = 1920 - 2 * sl["outer_padding"]
        gap = sl["grid_gap"]
        cell_w = (content_w - 2 * gap) // 3
        assert 3 * cell_w + 2 * gap <= content_w

    def test_3x4_cells_fit_in_content_area(self):
        """12 cells (3x4) + gaps should fit in content area."""
        h = 1080
        sl = _section_layout(h)
        content_w = 1920 - 2 * sl["outer_padding"]
        gap = sl["grid_gap"]
        cell_w = (content_w - 2 * gap) // 3
        assert 3 * cell_w + 2 * gap <= content_w

        header_frame = render_section_header_frame(
            title="Test", resolution=(1920, 1080),
            bg_color=TEST_BG, colors=TEST_COLORS,
        )
        header_h = header_frame.shape[0]
        content_h = h - header_h - sl["header_content_gap"] - sl["outer_padding"]
        cell_h = (content_h - 3 * gap) // 4
        assert 4 * cell_h + 3 * gap <= content_h
        assert cell_h > 50

    def test_cell_dimensions_positive_at_small_resolution(self):
        """Even at 270p, cells should have positive dimensions."""
        h = 270
        w = 480
        sl = _section_layout(h)
        content_w = w - 2 * sl["outer_padding"]
        gap = sl["grid_gap"]
        cell_w = (content_w - gap) // 2
        cell_h_area = h - sl["title_bar_h"] - sl["header_content_gap"] - sl["outer_padding"]
        cell_h = (cell_h_area - gap) // 2
        assert cell_w > 50
        assert cell_h > 30


class TestColumnHeaderLayout:
    """Test column header font scaling."""

    def test_col_header_font_scales_with_resolution(self):
        sl_1080 = _sec_scale(_REF_COL_HEADER_FONT_SIZE, 1080)
        sl_540 = _sec_scale(_REF_COL_HEADER_FONT_SIZE, 540)
        assert sl_1080 > sl_540
        assert sl_1080 == 22  # reference value at 1080p

    def test_col_header_font_respects_floor(self):
        sl_tiny = _sec_scale(_REF_COL_HEADER_FONT_SIZE, 100)
        assert sl_tiny >= 8  # floor value


class TestTitleCardLayout:
    """Test title_card font scaling."""

    def test_title_font_scales_with_resolution(self):
        sl_1080 = _sec_scale(_REF_TITLE_CARD_TITLE_FONT, 1080)
        sl_540 = _sec_scale(_REF_TITLE_CARD_TITLE_FONT, 540)
        assert sl_1080 > sl_540
        assert sl_1080 == 64  # reference value at 1080p

    def test_subtitle_font_scales_with_resolution(self):
        sl_1080 = _sec_scale(_REF_TITLE_CARD_SUBTITLE_FONT, 1080)
        sl_540 = _sec_scale(_REF_TITLE_CARD_SUBTITLE_FONT, 540)
        assert sl_1080 > sl_540
        assert sl_1080 == 36  # reference value at 1080p

    def test_title_card_has_accent_bar_at_top(self):
        """Top row of title card should contain accent color pixels."""
        from clipcompose.sections import render_title_card
        config = {"title": "Test Title", "duration": 2}
        video_settings = {
            "resolution": TEST_RESOLUTION,
            "fps": 30,
            "background": TEST_BG,
        }
        clip = render_title_card(config, video_settings, TEST_COLORS)
        frame = clip.get_frame(0)
        # Top-left pixel should be accent color.
        top_pixel = tuple(int(c) for c in frame[1, 100, :])
        assert top_pixel == TEST_COLORS["accent"]

    def test_title_card_underline_present(self):
        """Accent underline should appear between title and subtitle."""
        from clipcompose.sections import render_title_card
        config = {
            "title": "Test Title",
            "subtitle": "Subtitle text",
            "duration": 2,
        }
        video_settings = {
            "resolution": TEST_RESOLUTION,
            "fps": 30,
            "background": TEST_BG,
        }
        clip = render_title_card(config, video_settings, TEST_COLORS)
        frame = clip.get_frame(0)
        # The frame should contain accent-colored pixels in the middle
        # horizontal band (where the underline is). Check the center column.
        mid_col = frame[:, 960, :]
        accent = TEST_COLORS["accent"]
        accent_rows = [
            i for i in range(mid_col.shape[0])
            if tuple(int(c) for c in mid_col[i]) == accent
        ]
        # Should have accent pixels both at top (bar) and middle (underline).
        assert len(accent_rows) >= 2
        # Top accent bar and underline should be at different y regions.
        assert max(accent_rows) - min(accent_rows) > 50


class TestPaired2x2Layout:
    """Test paired_2x2 group layout math."""

    def test_group_gap_scales_with_resolution(self):
        gap_1080 = _sec_scale(_REF_GROUP_GAP, 1080)
        gap_540 = _sec_scale(_REF_GROUP_GAP, 540)
        assert gap_1080 > gap_540
        assert gap_1080 == 36  # reference value at 1080p

    def test_two_groups_fit_in_content_width(self):
        """Two groups + group_gap should fit within content width."""
        h = 1080
        sl = _section_layout(h)
        group_gap = _sec_scale(_REF_GROUP_GAP, h)
        content_w = 1920 - 2 * sl["outer_padding"]
        group_w = (content_w - group_gap) // 2
        assert 2 * group_w + group_gap <= content_w
        assert group_w > 200

    def test_cells_fit_within_group(self):
        """2x2 cells + gap should fit within each group's width."""
        h = 1080
        sl = _section_layout(h)
        group_gap = _sec_scale(_REF_GROUP_GAP, h)
        gap = sl["grid_gap"]
        content_w = 1920 - 2 * sl["outer_padding"]
        group_w = (content_w - group_gap) // 2
        cell_w = (group_w - gap) // 2
        assert 2 * cell_w + gap <= group_w
        assert cell_w > 100


class TestTextSlideLayout:
    """Test text_slide font and divider scaling."""

    def test_text_slide_font_scales_with_resolution(self):
        sl_1080 = _sec_scale(_REF_TEXT_SLIDE_FONT_SIZE, 1080)
        sl_540 = _sec_scale(_REF_TEXT_SLIDE_FONT_SIZE, 540)
        assert sl_1080 > sl_540

    def test_text_slide_divider_scales_with_resolution(self):
        sl_1080 = _sec_scale(_REF_TEXT_SLIDE_DIVIDER_W, 1080)
        sl_540 = _sec_scale(_REF_TEXT_SLIDE_DIVIDER_W, 540)
        assert sl_1080 >= sl_540

    def test_text_slide_renders_without_error(self):
        """Smoke test: render a 2-column text_slide."""
        from clipcompose.sections import render_text_slide
        config = {
            "header": "Key Findings",
            "subtitle": "Summary",
            "duration": 3,
            "columns": [
                {"lines": [
                    {"text": "Labeled Agent", "weight": "bold"},
                    {"text": "22D obs vector"},
                ]},
                {"lines": [
                    {"text": "Blind Agent", "weight": "bold", "color": "#e04c77"},
                    {"text": "15D obs vector"},
                ]},
            ],
        }
        video_settings = {
            "resolution": TEST_RESOLUTION,
            "fps": 30,
            "background": TEST_BG,
        }
        clip = render_text_slide(config, video_settings, TEST_COLORS)
        frame = clip.get_frame(0)
        assert frame.shape == (1080, 1920, 3)
        assert clip.duration == 3

    def test_text_slide_centered_text(self):
        """Centered text should be roughly centered in column (not left-hugging)."""
        from clipcompose.sections import render_text_slide
        config = {
            "header": "Centered",
            "duration": 2,
            "columns": [
                {"lines": [{"text": "Short"}], "align": "center"},
            ],
        }
        video_settings = {
            "resolution": TEST_RESOLUTION,
            "fps": 30,
            "background": TEST_BG,
        }
        clip = render_text_slide(config, video_settings, TEST_COLORS)
        frame = clip.get_frame(0)
        # Text should be roughly centered — check that leftmost non-bg pixel
        # in the text row is past the 1/4 mark of the frame.
        mid_row = frame.shape[0] // 2
        row = frame[mid_row, :, :]
        bg = np.array(TEST_BG)
        non_bg = np.where(np.any(row != bg, axis=1))[0]
        if len(non_bg) > 0:
            leftmost = non_bg[0]
            assert leftmost > frame.shape[1] // 4, (
                f"Centered text starts too far left: {leftmost}"
            )

    def test_text_slide_divider_present_for_2_columns(self):
        """2-column slide should have a divider (accent-ish pixels in the center)."""
        from clipcompose.sections import render_text_slide
        config = {
            "header": "Compare",
            "duration": 2,
            "columns": [
                {"lines": [{"text": "Left"}]},
                {"lines": [{"text": "Right"}]},
            ],
        }
        video_settings = {
            "resolution": TEST_RESOLUTION,
            "fps": 30,
            "background": TEST_BG,
        }
        clip = render_text_slide(config, video_settings, TEST_COLORS)
        frame = clip.get_frame(0)
        # Center vertical strip should have non-background pixels (divider).
        center_col = frame[540, :, :]  # middle row
        mid_x = 960
        # Check a small range around center for non-bg pixels.
        has_divider = False
        for x in range(mid_x - 5, mid_x + 5):
            pixel = tuple(int(c) for c in center_col[x])
            if pixel != TEST_BG:
                has_divider = True
                break
        assert has_divider
