"""Tests for clipcompose atoms — the AnnotatedClip unit.

Tests focus on the layout math (band sizing, clip placement) using
static frames, not actual video files. The atom renderer accepts a
bounding box and produces a composite at that size.

All tests pass a synthetic video aspect ratio (SRC_W x SRC_H) so
compute_annotation_band can compute the tight unit layout.
"""

import numpy as np
import pytest
from PIL import Image

from clipcompose.atoms import (
    compute_annotation_band,
    render_annotated_clip_frame,
)


# Standard test palette matching the manifest schema.
TEST_COLORS = {
    "text": (213, 213, 211),
    "text_secondary": (136, 136, 136),
    "landed": (80, 220, 120),
    "crashed": (240, 70, 70),
}

TEST_BG = (26, 26, 26)

# Synthetic source video dimensions (4:3 aspect ratio).
SRC_W, SRC_H = 640, 480

# Typical annotations list matching the manifest schema.
ANNOTS_BASIC = [
    {"text": "LANDED", "color": "#50DC78", "weight": "bold"},
    {"text": "g=-4.4 | autocorr=1.00"},
]

ANNOTS_DENSE = [
    {"text": "LANDED", "color": "#50DC78", "weight": "bold"},
    {"text": "g=-4.4"},
    {"text": "autocorr=1.00"},
    {"text": "fuel_eff=0.82"},
    {"text": "steps=142"},
]


class TestComputeAnnotationBand:
    """Test the layout math that sizes the annotation band."""

    def test_left_band_has_positive_width(self):
        band = compute_annotation_band(
            side="left",
            annotations=ANNOTS_BASIC,
            bbox_w=800,
            bbox_h=400,
            colors=TEST_COLORS,
            src_w=SRC_W,
            src_h=SRC_H,
        )
        assert band["band_w"] > 0
        # Band height matches scaled video height, not bbox height.
        assert band["band_h"] == band["clip_h"]

    def test_right_band_has_positive_width(self):
        band = compute_annotation_band(
            side="right",
            annotations=ANNOTS_BASIC,
            bbox_w=800,
            bbox_h=400,
            colors=TEST_COLORS,
            src_w=SRC_W,
            src_h=SRC_H,
        )
        assert band["band_w"] > 0
        assert band["band_h"] == band["clip_h"]

    def test_above_band_has_positive_height(self):
        band = compute_annotation_band(
            side="above",
            annotations=ANNOTS_BASIC,
            bbox_w=800,
            bbox_h=400,
            colors=TEST_COLORS,
            src_w=SRC_W,
            src_h=SRC_H,
        )
        assert band["band_w"] == band["clip_w"]
        assert band["band_h"] > 0

    def test_below_band_has_positive_height(self):
        band = compute_annotation_band(
            side="below",
            annotations=[{"text": "g=-4.4"}],
            bbox_w=800,
            bbox_h=400,
            colors=TEST_COLORS,
            src_w=SRC_W,
            src_h=SRC_H,
        )
        assert band["band_w"] == band["clip_w"]
        assert band["band_h"] > 0

    def test_band_does_not_exceed_max_fraction(self):
        """Band should never take more than 40% of the relevant axis."""
        band = compute_annotation_band(
            side="left",
            annotations=[{"text": "very long text " * 10}],
            bbox_w=400,
            bbox_h=300,
            colors=TEST_COLORS,
            src_w=SRC_W,
            src_h=SRC_H,
        )
        assert band["band_w"] <= 400 * 0.4 + 1  # +1 for rounding

    def test_no_annotations_still_has_min_band(self):
        """Even with no content, band has minimum size for visual consistency."""
        band = compute_annotation_band(
            side="left",
            annotations=[],
            bbox_w=800,
            bbox_h=400,
            colors=TEST_COLORS,
            src_w=SRC_W,
            src_h=SRC_H,
        )
        assert band["band_w"] >= 40  # minimum band width

    def test_unit_centered_in_bbox(self):
        """The tight unit (video + band) should be centered in the bbox."""
        band = compute_annotation_band(
            side="left",
            annotations=ANNOTS_BASIC,
            bbox_w=800,
            bbox_h=600,
            colors=TEST_COLORS,
            src_w=SRC_W,
            src_h=SRC_H,
        )
        left_margin = band["unit_x"]
        right_margin = 800 - band["unit_x"] - band["unit_w"]
        assert abs(left_margin - right_margin) <= 1
        top_margin = band["unit_y"]
        bottom_margin = 600 - band["unit_y"] - band["unit_h"]
        assert abs(top_margin - bottom_margin) <= 1

    def test_band_flush_with_video(self):
        """Band and video should touch — no gap between them."""
        for side_name in ("left", "right", "above", "below"):
            band = compute_annotation_band(
                side=side_name,
                annotations=ANNOTS_BASIC,
                bbox_w=800,
                bbox_h=600,
                colors=TEST_COLORS,
                src_w=SRC_W,
                src_h=SRC_H,
            )
            if side_name == "left":
                assert band["clip_x"] == band["band_x"] + band["band_w"]
            elif side_name == "right":
                assert band["band_x"] == band["clip_x"] + band["clip_w"]
            elif side_name == "above":
                assert band["clip_y"] == band["band_y"] + band["band_h"]
            elif side_name == "below":
                assert band["band_y"] == band["clip_y"] + band["clip_h"]

    def test_dense_annotations_produce_more_lines(self):
        """More annotation entries should produce more rendered lines."""
        band_basic = compute_annotation_band(
            side="left",
            annotations=ANNOTS_BASIC,
            bbox_w=800,
            bbox_h=600,
            colors=TEST_COLORS,
            src_w=SRC_W,
            src_h=SRC_H,
        )
        band_dense = compute_annotation_band(
            side="left",
            annotations=ANNOTS_DENSE,
            bbox_w=800,
            bbox_h=600,
            colors=TEST_COLORS,
            src_w=SRC_W,
            src_h=SRC_H,
        )
        assert len(band_basic["lines"]) == 2
        assert len(band_dense["lines"]) == 5


class TestRenderAnnotatedClipFrame:
    """Test that the static annotation frame renders correctly."""

    def test_returns_correct_shape(self):
        frame = render_annotated_clip_frame(
            bbox_w=800,
            bbox_h=400,
            side="left",
            annotations=ANNOTS_BASIC,
            bg_color=TEST_BG,
            colors=TEST_COLORS,
            src_w=SRC_W,
            src_h=SRC_H,
        )
        assert frame.shape == (400, 800, 3)
        assert frame.dtype == np.uint8

    def test_band_region_differs_from_bg(self):
        """The annotation band should have a different background than
        the section background, so it reads as part of the clip object."""
        band = compute_annotation_band(
            side="left",
            annotations=ANNOTS_BASIC,
            bbox_w=800,
            bbox_h=400,
            colors=TEST_COLORS,
            src_w=SRC_W,
            src_h=SRC_H,
        )
        frame = render_annotated_clip_frame(
            bbox_w=800,
            bbox_h=400,
            side="left",
            annotations=ANNOTS_BASIC,
            bg_color=TEST_BG,
            colors=TEST_COLORS,
            src_w=SRC_W,
            src_h=SRC_H,
        )
        mid_y = band["band_y"] + band["band_h"] // 2
        mid_x = band["band_x"] + 5
        band_pixel = tuple(frame[mid_y, mid_x, :])
        assert band_pixel != TEST_BG

    def test_all_four_sides(self):
        """Smoke test: all sides render without error."""
        for side in ("left", "right", "above", "below"):
            frame = render_annotated_clip_frame(
                bbox_w=800,
                bbox_h=400,
                side=side,
                annotations=ANNOTS_BASIC,
                bg_color=TEST_BG,
                colors=TEST_COLORS,
                src_w=SRC_W,
                src_h=SRC_H,
            )
            assert frame.shape == (400, 800, 3)
