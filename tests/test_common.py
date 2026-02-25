"""Tests for clipcompose.common utilities."""

import pytest
from PIL import Image

from clipcompose.common import (
    parse_hex_color,
    resolve_color,
    resolve_path_vars,
    load_font,
    render_text_on_image,
    load_clip,
)


class TestParseHexColor:
    def test_with_hash(self):
        assert parse_hex_color("#e04c77") == (224, 76, 119)

    def test_without_hash(self):
        assert parse_hex_color("1A1A1A") == (26, 26, 26)

    def test_black(self):
        assert parse_hex_color("#000000") == (0, 0, 0)

    def test_white(self):
        assert parse_hex_color("#FFFFFF") == (255, 255, 255)


class TestResolveColor:
    def test_palette_key(self):
        palette = {"blind": (224, 76, 119)}
        assert resolve_color("blind", palette) == (224, 76, 119)

    def test_inline_hex(self):
        assert resolve_color("#50DC78", {}) == (80, 220, 120)

    def test_unknown_key_raises(self):
        with pytest.raises(ValueError, match="Unknown color"):
            resolve_color("nonexistent", {})


class TestResolvePathVars:
    def test_single_var(self):
        result = resolve_path_vars("${videos}/grid1", {"videos": "/data/vids"})
        assert result == "/data/vids/grid1"

    def test_multiple_vars(self):
        paths = {"videos": "/data/vids", "figures": "/data/figs"}
        result = resolve_path_vars("${videos}/a and ${figures}/b", paths)
        assert result == "/data/vids/a and /data/figs/b"

    def test_no_vars(self):
        assert resolve_path_vars("/plain/path", {}) == "/plain/path"

    def test_unknown_var_raises(self):
        with pytest.raises(ValueError, match="Unknown path variable"):
            resolve_path_vars("${missing}/x", {})


class TestLoadFont:
    def test_returns_font_object(self):
        font = load_font(size=24)
        assert font is not None

    def test_different_sizes(self):
        small = load_font(size=12)
        large = load_font(size=48)
        assert small is not None
        assert large is not None


class TestRenderTextOnImage:
    def test_renders_without_error(self):
        img = Image.new("RGB", (400, 100), (0, 0, 0))
        font = load_font(size=20)
        height = render_text_on_image(
            img, "test text", (10, 10), font, (255, 255, 255),
        )
        assert height > 0

    def test_truncates_long_text(self):
        img = Image.new("RGB", (100, 50), (0, 0, 0))
        font = load_font(size=20)
        render_text_on_image(
            img, "very long text that should be truncated", (0, 0),
            font, (255, 255, 255), max_width=80,
        )
        # Should not raise -- just truncates with ellipsis.


class TestLoadClip:
    def test_loads_and_resamples(self, tmp_path):
        """Create a tiny mp4, load it with load_clip, verify fps resampling."""
        import numpy as np
        from moviepy import ImageClip

        # Create a 1-second test clip at 50fps, write to temp file.
        frame = np.zeros((64, 64, 3), dtype=np.uint8)
        test_mp4 = str(tmp_path / "test.mp4")
        ImageClip(frame).with_duration(1.0).with_fps(50).write_videofile(
            test_mp4, fps=50, codec="libx264", audio=False, logger=None,
        )

        clip = load_clip(test_mp4, target_fps=30)
        assert clip.fps == 30
        assert clip.duration > 0
        clip.close()
