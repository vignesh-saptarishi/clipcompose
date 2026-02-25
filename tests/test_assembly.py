"""Tests for assembly pipeline -- temporal composition.

Verifies that assemble_sections correctly handles:
  - Single-section passthrough
  - Crossfade overlap (total duration < sum of clip durations)
  - Hard cut (total duration = sum of clip durations)
  - Fade-to-black without overlap (total = sum)
  - Mixed transition types in a multi-section timeline
  - Empty input rejection
"""

import numpy as np
import pytest
from moviepy import ImageClip

from clipcompose.assembly import assemble_sections


def _color_clip(color, duration=2.0, size=(320, 240), fps=30):
    """Create a solid-color clip for testing."""
    frame = np.full((*size[::-1], 3), color, dtype=np.uint8)
    return ImageClip(frame).with_duration(duration).with_fps(fps)


class TestAssembleSections:
    def test_single_section_returns_unchanged(self):
        clip = _color_clip((255, 0, 0), duration=3.0)
        sections = [{"clip": clip, "transition": 0.5, "transition_type": "crossfade"}]
        result = assemble_sections(sections, fps=30)
        assert abs(result.duration - 3.0) < 0.1

    def test_two_sections_crossfade_shorter_than_sum(self):
        """Crossfade overlaps clips, so total < sum of durations."""
        c1 = _color_clip((255, 0, 0), duration=3.0)
        c2 = _color_clip((0, 0, 255), duration=3.0)
        sections = [
            {"clip": c1, "transition": 0.5, "transition_type": "crossfade"},
            {"clip": c2, "transition": 0.5, "transition_type": "crossfade"},
        ]
        result = assemble_sections(sections, fps=30)
        # 3.0 + 3.0 - 0.5 overlap = 5.5s
        assert abs(result.duration - 5.5) < 0.2

    def test_two_sections_cut_equals_sum(self):
        """Hard cut = no overlap, total equals sum of durations."""
        c1 = _color_clip((255, 0, 0), duration=2.0)
        c2 = _color_clip((0, 0, 255), duration=2.0)
        sections = [
            {"clip": c1, "transition": 0, "transition_type": "crossfade"},
            {"clip": c2, "transition": 0, "transition_type": "crossfade"},
        ]
        result = assemble_sections(sections, fps=30)
        assert abs(result.duration - 4.0) < 0.2

    def test_fade_to_black_equals_sum(self):
        """Fade-to-black has no overlap -- total equals sum of durations."""
        c1 = _color_clip((255, 0, 0), duration=3.0)
        c2 = _color_clip((0, 0, 255), duration=3.0)
        sections = [
            {"clip": c1, "transition": 1.0, "transition_type": "fade_to_black"},
            {"clip": c2, "transition": 1.0, "transition_type": "fade_to_black"},
        ]
        result = assemble_sections(sections, fps=30)
        # No overlap: 3.0 + 3.0 = 6.0s
        assert abs(result.duration - 6.0) < 0.2

    def test_mixed_transitions(self):
        """Mix of crossfade and cut transitions."""
        c1 = _color_clip((255, 0, 0), duration=2.0)
        c2 = _color_clip((0, 255, 0), duration=2.0)
        c3 = _color_clip((0, 0, 255), duration=2.0)
        sections = [
            {"clip": c1, "transition": 0, "transition_type": "crossfade"},
            {"clip": c2, "transition": 0.5, "transition_type": "crossfade"},
            {"clip": c3, "transition": 0.5, "transition_type": "crossfade"},
        ]
        result = assemble_sections(sections, fps=30)
        # c1->c2 is cut (transition=0): no overlap.
        # c2->c3 is crossfade (transition=0.5): 0.5s overlap.
        # Total: 2.0 + 2.0 + 2.0 - 0.5 = 5.5s
        assert abs(result.duration - 5.5) < 0.2

    def test_empty_sections_raises(self):
        with pytest.raises(ValueError, match="No sections"):
            assemble_sections([], fps=30)
