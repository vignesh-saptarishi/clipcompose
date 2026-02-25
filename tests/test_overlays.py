"""Tests for clipcompose overlay rendering."""

import numpy as np
import pytest
from PIL import Image

from clipcompose.overlays import (
    apply_overlays_to_frame,
    compute_overlay_position,
    render_overlay_patch,
    OVERLAY_MARGIN_FRAC,
)


TEST_COLORS = {
    "text": (213, 213, 211),
    "text_secondary": (136, 136, 136),
    "accent": (177, 19, 77),
}


class TestComputeOverlayPosition:
    """Test 3x3 grid position computation."""

    def test_top_left(self):
        x, y = compute_overlay_position(
            "top-left", patch_w=100, patch_h=30, frame_w=1920, frame_h=1080,
        )
        margin_x = int(1920 * OVERLAY_MARGIN_FRAC)
        margin_y = int(1080 * OVERLAY_MARGIN_FRAC)
        assert x == margin_x
        assert y == margin_y

    def test_bottom_right(self):
        x, y = compute_overlay_position(
            "bottom-right", patch_w=100, patch_h=30, frame_w=1920, frame_h=1080,
        )
        margin_x = int(1920 * OVERLAY_MARGIN_FRAC)
        margin_y = int(1080 * OVERLAY_MARGIN_FRAC)
        assert x == 1920 - margin_x - 100
        assert y == 1080 - margin_y - 30

    def test_middle_center(self):
        x, y = compute_overlay_position(
            "middle-center", patch_w=100, patch_h=30, frame_w=1920, frame_h=1080,
        )
        assert x == (1920 - 100) // 2
        assert y == (1080 - 30) // 2

    def test_top_center(self):
        x, y = compute_overlay_position(
            "top-center", patch_w=100, patch_h=30, frame_w=1920, frame_h=1080,
        )
        margin_y = int(1080 * OVERLAY_MARGIN_FRAC)
        assert x == (1920 - 100) // 2
        assert y == margin_y


class TestRenderOverlayPatch:
    """Test overlay patch rendering."""

    def test_returns_rgba_array(self):
        patch = render_overlay_patch(
            text="Test", font_size=24, color=(255, 255, 255),
            rotation=0,
        )
        assert patch.shape[2] == 4  # RGBA
        assert patch.dtype == np.uint8

    def test_rotation_swaps_dimensions(self):
        patch_0 = render_overlay_patch(
            text="Long text here", font_size=24, color=(255, 255, 255),
            rotation=0,
        )
        patch_90 = render_overlay_patch(
            text="Long text here", font_size=24, color=(255, 255, 255),
            rotation=90,
        )
        # After 90-degree rotation, width and height should swap (approximately).
        assert abs(patch_0.shape[0] - patch_90.shape[1]) < 5
        assert abs(patch_0.shape[1] - patch_90.shape[0]) < 5

    def test_has_semi_transparent_background(self):
        patch = render_overlay_patch(
            text="Test", font_size=24, color=(255, 255, 255),
            rotation=0,
        )
        # Alpha channel should have values between 0 and 255 (semi-transparent).
        alpha = patch[:, :, 3]
        assert alpha.max() > 0
        assert alpha.min() == 0  # corners should be transparent


class TestOverlayPositionWithRegion:
    """Test 3x3 grid positioning constrained to a sub-region."""

    def test_top_left_in_region(self):
        """top-left should be at region origin + margin, not frame origin."""
        x, y = compute_overlay_position(
            "top-left", patch_w=50, patch_h=20, frame_w=1920, frame_h=1080,
            region=(100, 200, 800, 600),
        )
        margin_x = int(800 * OVERLAY_MARGIN_FRAC)
        margin_y = int(600 * OVERLAY_MARGIN_FRAC)
        assert x == 100 + margin_x
        assert y == 200 + margin_y

    def test_bottom_right_in_region(self):
        x, y = compute_overlay_position(
            "bottom-right", patch_w=50, patch_h=20, frame_w=1920, frame_h=1080,
            region=(100, 200, 800, 600),
        )
        margin_x = int(800 * OVERLAY_MARGIN_FRAC)
        margin_y = int(600 * OVERLAY_MARGIN_FRAC)
        assert x == 100 + 800 - margin_x - 50
        assert y == 200 + 600 - margin_y - 20

    def test_middle_center_in_region(self):
        x, y = compute_overlay_position(
            "middle-center", patch_w=50, patch_h=20, frame_w=1920, frame_h=1080,
            region=(100, 200, 800, 600),
        )
        assert x == 100 + (800 - 50) // 2
        assert y == 200 + (600 - 20) // 2

    def test_no_region_uses_full_frame(self):
        """Backwards compat: no region = same as before."""
        x1, y1 = compute_overlay_position(
            "top-left", patch_w=50, patch_h=20, frame_w=1920, frame_h=1080,
        )
        x2, y2 = compute_overlay_position(
            "top-left", patch_w=50, patch_h=20, frame_w=1920, frame_h=1080,
            region=None,
        )
        assert (x1, y1) == (x2, y2)


class TestApplyOverlaysToFrame:
    """Integration tests for overlay application to frames."""

    def test_overlay_modifies_frame(self):
        """Applying an overlay should change some pixels in the frame."""
        frame = np.full((400, 600, 3), 26, dtype=np.uint8)  # dark bg
        overlay_items = [
            {"text": "TEST", "position": "middle-center"},
        ]
        colors = {"text": (255, 255, 255)}
        result = apply_overlays_to_frame(frame, overlay_items, colors, font_size=20)
        assert not np.array_equal(frame, result)

    def test_rotated_overlay_modifies_frame(self):
        """A rotated overlay should also modify pixels."""
        frame = np.full((400, 600, 3), 26, dtype=np.uint8)
        overlay_items = [
            {"text": "ROTATED", "position": "middle-left", "rotation": -90},
        ]
        colors = {"text": (255, 255, 255)}
        result = apply_overlays_to_frame(frame, overlay_items, colors, font_size=20)
        assert not np.array_equal(frame, result)

    def test_rotated_overlay_at_left_is_taller_than_wide(self):
        """A -90 rotation at middle-left should produce a vertically-oriented patch."""
        patch = render_overlay_patch(
            text="Long label text", font_size=20,
            color=(255, 255, 255), rotation=-90,
        )
        # Rotated patch should be taller than wide (text was horizontal, now vertical).
        assert patch.shape[0] > patch.shape[1]

    def test_overlay_with_region(self):
        """Overlay in a region should only modify pixels within that region."""
        frame = np.full((400, 600, 3), 26, dtype=np.uint8)
        overlay_items = [
            {"text": "IN REGION", "position": "top-left"},
        ]
        colors = {"text": (255, 255, 255)}
        region = (200, 100, 300, 200)  # overlay restricted to right half
        result = apply_overlays_to_frame(
            frame, overlay_items, colors, font_size=16, region=region,
        )
        # Left portion (x < 200) should be unchanged.
        assert np.array_equal(frame[:, :200, :], result[:, :200, :])
        # Region area should have some changed pixels.
        assert not np.array_equal(
            frame[100:300, 200:500, :], result[100:300, 200:500, :],
        )
