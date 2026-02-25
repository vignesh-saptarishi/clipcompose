"""Tests for clipcompose manifest loader."""

import tempfile

import pytest
import yaml

from clipcompose.manifest import (
    load_manifest,
    validate_paths,
)


def _write_manifest(content: dict) -> str:
    """Write a manifest dict to a temp YAML file, return path."""
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
    yaml.dump(content, f)
    f.close()
    return f.name


def _minimal_manifest(**overrides):
    """Return a minimal valid manifest dict with one single_clip section."""
    m = {
        "video": {
            "resolution": [1920, 1080],
            "fps": 30,
            "background": "#1A1A1A",
        },
        "colors": {
            "text": "#D5D5D3",
            "text_secondary": "#888888",
            "accent": "#B1134D",
            "landed": "#50DC78",
            "crashed": "#F04646",
        },
        "sections": [],
    }
    m.update(overrides)
    return m


def _single_clip_section(**overrides):
    """Return a minimal valid single_clip section."""
    s = {
        "template": "single_clip",
        "header": "Test Header",
        "clip": {
            "path": "/tmp/fake.mp4",
            "annotation_side": "left",
        },
    }
    s.update(overrides)
    return s


class TestLoadManifest:
    def test_parses_resolution_as_tuple(self):
        path = _write_manifest(_minimal_manifest())
        config = load_manifest(path)
        assert config["video"]["resolution"] == (1920, 1080)

    def test_parses_background_color(self):
        path = _write_manifest(_minimal_manifest())
        config = load_manifest(path)
        assert config["video"]["background"] == (26, 26, 26)

    def test_parses_palette_colors(self):
        path = _write_manifest(_minimal_manifest())
        config = load_manifest(path)
        assert config["colors"]["landed"] == (80, 220, 120)
        assert config["colors"]["crashed"] == (240, 70, 70)

    def test_resolves_path_variables(self):
        manifest = _minimal_manifest(
            paths={"videos": "/data/vids"},
            sections=[_single_clip_section(
                clip={"path": "${videos}/test.mp4", "annotation_side": "left"},
            )],
        )
        path = _write_manifest(manifest)
        config = load_manifest(path)
        assert config["sections"][0]["clip"]["path"] == "/data/vids/test.mp4"

    def test_unknown_template_raises(self):
        manifest = _minimal_manifest(
            sections=[{"template": "nonexistent"}],
        )
        path = _write_manifest(manifest)
        with pytest.raises(ValueError, match="Unknown template"):
            load_manifest(path)


class TestValidateSingleClip:
    def test_missing_clip_raises(self):
        manifest = _minimal_manifest(
            sections=[{"template": "single_clip", "header": "X"}],
        )
        path = _write_manifest(manifest)
        with pytest.raises(ValueError, match="clip"):
            load_manifest(path)

    def test_missing_annotation_side_raises(self):
        manifest = _minimal_manifest(
            sections=[{
                "template": "single_clip",
                "header": "X",
                "clip": {"path": "/tmp/fake.mp4"},
            }],
        )
        path = _write_manifest(manifest)
        with pytest.raises(ValueError, match="annotation_side"):
            load_manifest(path)

    def test_invalid_annotation_side_raises(self):
        manifest = _minimal_manifest(
            sections=[_single_clip_section(
                clip={"path": "/tmp/fake.mp4", "annotation_side": "middle"},
            )],
        )
        path = _write_manifest(manifest)
        with pytest.raises(ValueError, match="annotation_side"):
            load_manifest(path)

    def test_annotation_missing_text_raises(self):
        manifest = _minimal_manifest(
            sections=[_single_clip_section(
                clip={
                    "path": "/tmp/fake.mp4",
                    "annotation_side": "left",
                    "annotations": [{"weight": "bold"}],
                },
            )],
        )
        path = _write_manifest(manifest)
        with pytest.raises(ValueError, match="missing 'text'"):
            load_manifest(path)

    def test_invalid_weight_raises(self):
        manifest = _minimal_manifest(
            sections=[_single_clip_section(
                clip={
                    "path": "/tmp/fake.mp4",
                    "annotation_side": "left",
                    "annotations": [{"text": "ok", "weight": "italic"}],
                },
            )],
        )
        path = _write_manifest(manifest)
        with pytest.raises(ValueError, match="weight"):
            load_manifest(path)

    def test_valid_annotations_accepted(self):
        manifest = _minimal_manifest(
            sections=[_single_clip_section(
                clip={
                    "path": "/tmp/fake.mp4",
                    "annotation_side": "left",
                    "annotations": [
                        {"text": "LANDED", "color": "#50DC78", "weight": "bold"},
                        {"text": "g=-4.4"},
                    ],
                },
            )],
        )
        path = _write_manifest(manifest)
        config = load_manifest(path)
        annots = config["sections"][0]["clip"]["annotations"]
        assert len(annots) == 2
        assert annots[0]["text"] == "LANDED"

    def test_valid_sides_accepted(self):
        for side in ("left", "right", "above", "below"):
            manifest = _minimal_manifest(
                sections=[_single_clip_section(
                    clip={
                        "path": "/tmp/fake.mp4",
                        "annotation_side": side,
                    },
                )],
            )
            path = _write_manifest(manifest)
            config = load_manifest(path)
            assert config["sections"][0]["clip"]["annotation_side"] == side


def _grid_clip(**overrides):
    """Return a minimal valid clip dict for grid templates."""
    c = {"path": "/tmp/fake.mp4", "annotation_side": "left"}
    c.update(overrides)
    return c


class TestValidateGrid:
    def test_grid_2x1_accepts_2_clips(self):
        manifest = _minimal_manifest(
            sections=[{
                "template": "grid_2x1",
                "header": "Side by Side",
                "clips": [_grid_clip(), _grid_clip()],
            }],
        )
        path = _write_manifest(manifest)
        config = load_manifest(path)
        assert len(config["sections"][0]["clips"]) == 2

    def test_grid_2x1_wrong_count_raises(self):
        manifest = _minimal_manifest(
            sections=[{
                "template": "grid_2x1",
                "header": "X",
                "clips": [_grid_clip()],
            }],
        )
        path = _write_manifest(manifest)
        with pytest.raises(ValueError, match="2 clips"):
            load_manifest(path)

    def test_grid_2x2_accepts_4_clips(self):
        manifest = _minimal_manifest(
            sections=[{
                "template": "grid_2x2",
                "header": "Grid",
                "clips": [_grid_clip() for _ in range(4)],
            }],
        )
        path = _write_manifest(manifest)
        config = load_manifest(path)
        assert len(config["sections"][0]["clips"]) == 4

    def test_grid_2x2_wrong_count_raises(self):
        manifest = _minimal_manifest(
            sections=[{
                "template": "grid_2x2",
                "header": "X",
                "clips": [_grid_clip() for _ in range(3)],
            }],
        )
        path = _write_manifest(manifest)
        with pytest.raises(ValueError, match="4 clips"):
            load_manifest(path)

    def test_grid_missing_clips_raises(self):
        manifest = _minimal_manifest(
            sections=[{
                "template": "grid_2x1",
                "header": "X",
            }],
        )
        path = _write_manifest(manifest)
        with pytest.raises(ValueError, match="clips"):
            load_manifest(path)

    def test_grid_3x1_accepts_3_clips(self):
        manifest = _minimal_manifest(
            sections=[{
                "template": "grid_3x1",
                "header": "Three columns",
                "clips": [_grid_clip() for _ in range(3)],
            }],
        )
        path = _write_manifest(manifest)
        config = load_manifest(path)
        assert len(config["sections"][0]["clips"]) == 3

    def test_grid_3x1_wrong_count_raises(self):
        manifest = _minimal_manifest(
            sections=[{
                "template": "grid_3x1",
                "header": "X",
                "clips": [_grid_clip() for _ in range(2)],
            }],
        )
        path = _write_manifest(manifest)
        with pytest.raises(ValueError, match="3 clips"):
            load_manifest(path)

    def test_grid_2x4_accepts_8_clips(self):
        manifest = _minimal_manifest(
            sections=[{
                "template": "grid_2x4",
                "header": "Eight clips",
                "clips": [_grid_clip() for _ in range(8)],
            }],
        )
        path = _write_manifest(manifest)
        config = load_manifest(path)
        assert len(config["sections"][0]["clips"]) == 8

    def test_grid_3x4_accepts_12_clips(self):
        manifest = _minimal_manifest(
            sections=[{
                "template": "grid_3x4",
                "header": "Twelve clips",
                "clips": [_grid_clip() for _ in range(12)],
            }],
        )
        path = _write_manifest(manifest)
        config = load_manifest(path)
        assert len(config["sections"][0]["clips"]) == 12

    def test_grid_3x4_wrong_count_raises(self):
        manifest = _minimal_manifest(
            sections=[{
                "template": "grid_3x4",
                "header": "X",
                "clips": [_grid_clip() for _ in range(11)],
            }],
        )
        path = _write_manifest(manifest)
        with pytest.raises(ValueError, match="12 clips"):
            load_manifest(path)

    def test_column_headers_accepted(self):
        manifest = _minimal_manifest(
            sections=[{
                "template": "grid_3x1",
                "header": "Three Variants",
                "column_headers": ["Labeled", "Blind", "History"],
                "clips": [_grid_clip() for _ in range(3)],
            }],
        )
        path = _write_manifest(manifest)
        config = load_manifest(path)
        assert config["sections"][0]["column_headers"] == ["Labeled", "Blind", "History"]

    def test_column_headers_wrong_count_raises(self):
        manifest = _minimal_manifest(
            sections=[{
                "template": "grid_2x1",
                "header": "X",
                "column_headers": ["A", "B", "C"],
                "clips": [_grid_clip(), _grid_clip()],
            }],
        )
        path = _write_manifest(manifest)
        with pytest.raises(ValueError, match="column_headers requires exactly 2"):
            load_manifest(path)

    def test_column_headers_non_list_raises(self):
        manifest = _minimal_manifest(
            sections=[{
                "template": "grid_2x1",
                "header": "X",
                "column_headers": "not a list",
                "clips": [_grid_clip(), _grid_clip()],
            }],
        )
        path = _write_manifest(manifest)
        with pytest.raises(ValueError, match="column_headers.*must be a list"):
            load_manifest(path)

    def test_column_headers_non_string_raises(self):
        manifest = _minimal_manifest(
            sections=[{
                "template": "grid_2x1",
                "header": "X",
                "column_headers": ["A", 42],
                "clips": [_grid_clip(), _grid_clip()],
            }],
        )
        path = _write_manifest(manifest)
        with pytest.raises(ValueError, match="column_headers.*must be a string"):
            load_manifest(path)

    def test_column_headers_2x4_accepts_2(self):
        manifest = _minimal_manifest(
            sections=[{
                "template": "grid_2x4",
                "header": "Two columns",
                "column_headers": ["Left", "Right"],
                "clips": [_grid_clip() for _ in range(8)],
            }],
        )
        path = _write_manifest(manifest)
        config = load_manifest(path)
        assert len(config["sections"][0]["column_headers"]) == 2

    def test_grid_clip_validation_runs(self):
        manifest = _minimal_manifest(
            sections=[{
                "template": "grid_2x1",
                "header": "X",
                "clips": [
                    _grid_clip(),
                    _grid_clip(annotation_side="middle"),
                ],
            }],
        )
        path = _write_manifest(manifest)
        with pytest.raises(ValueError, match="annotation_side"):
            load_manifest(path)


class TestValidateTitleCard:
    def test_valid_title_card_accepted(self):
        manifest = _minimal_manifest(
            sections=[{
                "template": "title_card",
                "title": "Latent World Geometry",
                "duration": 8,
            }],
        )
        path = _write_manifest(manifest)
        config = load_manifest(path)
        assert config["sections"][0]["title"] == "Latent World Geometry"

    def test_title_card_with_subtitle(self):
        manifest = _minimal_manifest(
            sections=[{
                "template": "title_card",
                "title": "Main Title",
                "subtitle": "A subtitle",
                "duration": 5,
            }],
        )
        path = _write_manifest(manifest)
        config = load_manifest(path)
        assert config["sections"][0]["subtitle"] == "A subtitle"

    def test_missing_title_raises(self):
        manifest = _minimal_manifest(
            sections=[{
                "template": "title_card",
                "duration": 5,
            }],
        )
        path = _write_manifest(manifest)
        with pytest.raises(ValueError, match="title"):
            load_manifest(path)

    def test_missing_duration_raises(self):
        manifest = _minimal_manifest(
            sections=[{
                "template": "title_card",
                "title": "Test",
            }],
        )
        path = _write_manifest(manifest)
        with pytest.raises(ValueError, match="duration"):
            load_manifest(path)

    def test_non_positive_duration_raises(self):
        manifest = _minimal_manifest(
            sections=[{
                "template": "title_card",
                "title": "Test",
                "duration": 0,
            }],
        )
        path = _write_manifest(manifest)
        with pytest.raises(ValueError, match="duration"):
            load_manifest(path)


def _paired_group(**overrides):
    """Return a minimal valid group dict for paired_2x2."""
    g = {
        "header": "Group",
        "clips": [_grid_clip() for _ in range(4)],
    }
    g.update(overrides)
    return g


class TestValidatePaired2x2:
    def test_valid_paired_2x2_accepted(self):
        manifest = _minimal_manifest(
            sections=[{
                "template": "paired_2x2",
                "header": "Comparison",
                "groups": [_paired_group(header="A"), _paired_group(header="B")],
            }],
        )
        path = _write_manifest(manifest)
        config = load_manifest(path)
        assert len(config["sections"][0]["groups"]) == 2

    def test_missing_groups_raises(self):
        manifest = _minimal_manifest(
            sections=[{
                "template": "paired_2x2",
                "header": "X",
            }],
        )
        path = _write_manifest(manifest)
        with pytest.raises(ValueError, match="groups"):
            load_manifest(path)

    def test_wrong_group_count_raises(self):
        manifest = _minimal_manifest(
            sections=[{
                "template": "paired_2x2",
                "header": "X",
                "groups": [_paired_group()],
            }],
        )
        path = _write_manifest(manifest)
        with pytest.raises(ValueError, match="2 groups"):
            load_manifest(path)

    def test_group_missing_header_raises(self):
        manifest = _minimal_manifest(
            sections=[{
                "template": "paired_2x2",
                "header": "X",
                "groups": [
                    _paired_group(),
                    {"clips": [_grid_clip() for _ in range(4)]},
                ],
            }],
        )
        path = _write_manifest(manifest)
        with pytest.raises(ValueError, match="header"):
            load_manifest(path)

    def test_group_wrong_clip_count_raises(self):
        manifest = _minimal_manifest(
            sections=[{
                "template": "paired_2x2",
                "header": "X",
                "groups": [
                    _paired_group(),
                    _paired_group(clips=[_grid_clip() for _ in range(3)]),
                ],
            }],
        )
        path = _write_manifest(manifest)
        with pytest.raises(ValueError, match="4 clips"):
            load_manifest(path)

    def test_group_clip_validation_runs(self):
        manifest = _minimal_manifest(
            sections=[{
                "template": "paired_2x2",
                "header": "X",
                "groups": [
                    _paired_group(),
                    _paired_group(clips=[
                        _grid_clip(), _grid_clip(),
                        _grid_clip(annotation_side="middle"), _grid_clip(),
                    ]),
                ],
            }],
        )
        path = _write_manifest(manifest)
        with pytest.raises(ValueError, match="annotation_side"):
            load_manifest(path)


def _text_slide_section(**overrides):
    """Return a minimal valid text_slide section."""
    s = {
        "template": "text_slide",
        "header": "Key Findings",
        "duration": 8,
        "columns": [
            {"lines": [{"text": "Finding one"}, {"text": "Finding two"}]},
        ],
    }
    s.update(overrides)
    return s


class TestValidateTextSlide:
    def test_valid_1_column_accepted(self):
        manifest = _minimal_manifest(
            sections=[_text_slide_section()],
        )
        path = _write_manifest(manifest)
        config = load_manifest(path)
        assert len(config["sections"][0]["columns"]) == 1

    def test_valid_2_columns_accepted(self):
        manifest = _minimal_manifest(
            sections=[_text_slide_section(columns=[
                {"lines": [{"text": "Col 1"}]},
                {"lines": [{"text": "Col 2"}]},
            ])],
        )
        path = _write_manifest(manifest)
        config = load_manifest(path)
        assert len(config["sections"][0]["columns"]) == 2

    def test_valid_3_columns_accepted(self):
        manifest = _minimal_manifest(
            sections=[_text_slide_section(columns=[
                {"lines": [{"text": "Col 1"}]},
                {"lines": [{"text": "Col 2"}]},
                {"lines": [{"text": "Col 3"}]},
            ])],
        )
        path = _write_manifest(manifest)
        config = load_manifest(path)
        assert len(config["sections"][0]["columns"]) == 3

    def test_missing_columns_raises(self):
        section = _text_slide_section()
        del section["columns"]
        manifest = _minimal_manifest(sections=[section])
        path = _write_manifest(manifest)
        with pytest.raises(ValueError, match="columns"):
            load_manifest(path)

    def test_missing_duration_raises(self):
        section = _text_slide_section()
        del section["duration"]
        manifest = _minimal_manifest(sections=[section])
        path = _write_manifest(manifest)
        with pytest.raises(ValueError, match="duration"):
            load_manifest(path)

    def test_zero_columns_raises(self):
        manifest = _minimal_manifest(
            sections=[_text_slide_section(columns=[])],
        )
        path = _write_manifest(manifest)
        with pytest.raises(ValueError, match="1.*3 columns"):
            load_manifest(path)

    def test_four_columns_raises(self):
        manifest = _minimal_manifest(
            sections=[_text_slide_section(columns=[
                {"lines": [{"text": f"Col {i}"}]} for i in range(4)
            ])],
        )
        path = _write_manifest(manifest)
        with pytest.raises(ValueError, match="1.*3 columns"):
            load_manifest(path)

    def test_column_missing_lines_raises(self):
        manifest = _minimal_manifest(
            sections=[_text_slide_section(columns=[
                {"header": "no lines here"},
            ])],
        )
        path = _write_manifest(manifest)
        with pytest.raises(ValueError, match="lines"):
            load_manifest(path)

    def test_line_missing_text_raises(self):
        manifest = _minimal_manifest(
            sections=[_text_slide_section(columns=[
                {"lines": [{"weight": "bold"}]},
            ])],
        )
        path = _write_manifest(manifest)
        with pytest.raises(ValueError, match="text"):
            load_manifest(path)

    def test_line_invalid_weight_raises(self):
        manifest = _minimal_manifest(
            sections=[_text_slide_section(columns=[
                {"lines": [{"text": "ok", "weight": "italic"}]},
            ])],
        )
        path = _write_manifest(manifest)
        with pytest.raises(ValueError, match="weight"):
            load_manifest(path)

    def test_line_with_color_and_weight_accepted(self):
        manifest = _minimal_manifest(
            sections=[_text_slide_section(columns=[
                {"lines": [
                    {"text": "Important", "color": "#FF0000", "weight": "bold"},
                    {"text": "Normal line"},
                ]},
            ])],
        )
        path = _write_manifest(manifest)
        config = load_manifest(path)
        lines = config["sections"][0]["columns"][0]["lines"]
        assert len(lines) == 2
        assert lines[0]["weight"] == "bold"

    def test_column_align_left_accepted(self):
        manifest = _minimal_manifest(
            sections=[_text_slide_section(columns=[
                {"lines": [{"text": "Left aligned"}], "align": "left"},
            ])],
        )
        path = _write_manifest(manifest)
        config = load_manifest(path)
        assert config["sections"][0]["columns"][0]["align"] == "left"

    def test_column_align_center_accepted(self):
        manifest = _minimal_manifest(
            sections=[_text_slide_section(columns=[
                {"lines": [{"text": "Centered"}], "align": "center"},
            ])],
        )
        path = _write_manifest(manifest)
        config = load_manifest(path)
        assert config["sections"][0]["columns"][0]["align"] == "center"

    def test_column_align_invalid_raises(self):
        manifest = _minimal_manifest(
            sections=[_text_slide_section(columns=[
                {"lines": [{"text": "Bad"}], "align": "right"},
            ])],
        )
        path = _write_manifest(manifest)
        with pytest.raises(ValueError, match="align"):
            load_manifest(path)


class TestValidatePaths:
    def test_missing_path_raises(self):
        config = {
            "sections": [{
                "clip": {"path": "/nonexistent/fake.mp4"},
            }],
        }
        with pytest.raises(FileNotFoundError, match="fake.mp4"):
            validate_paths(config)

    def test_existing_path_passes(self, tmp_path):
        mp4 = tmp_path / "test.mp4"
        mp4.write_bytes(b"fake")
        config = {
            "sections": [{
                "clip": {"path": str(mp4)},
            }],
        }
        validate_paths(config)  # Should not raise.


class TestValidateOverlay:
    """Test overlay validation for per-clip and section-level overlays."""

    def test_clip_overlay_accepted(self):
        manifest = _minimal_manifest(
            sections=[_single_clip_section(
                clip={
                    "path": "/tmp/fake.mp4",
                    "annotation_side": "left",
                    "overlay": [
                        {"text": "g=-4.4", "position": "bottom-left"},
                    ],
                },
            )],
        )
        path = _write_manifest(manifest)
        config = load_manifest(path)
        assert len(config["sections"][0]["clip"]["overlay"]) == 1

    def test_clip_overlay_all_positions_accepted(self):
        positions = [
            "top-left", "top-center", "top-right",
            "middle-left", "middle-center", "middle-right",
            "bottom-left", "bottom-center", "bottom-right",
        ]
        for pos in positions:
            manifest = _minimal_manifest(
                sections=[_single_clip_section(
                    clip={
                        "path": "/tmp/fake.mp4",
                        "annotation_side": "left",
                        "overlay": [{"text": "test", "position": pos}],
                    },
                )],
            )
            path = _write_manifest(manifest)
            config = load_manifest(path)
            assert config["sections"][0]["clip"]["overlay"][0]["position"] == pos

    def test_clip_overlay_invalid_position_raises(self):
        manifest = _minimal_manifest(
            sections=[_single_clip_section(
                clip={
                    "path": "/tmp/fake.mp4",
                    "annotation_side": "left",
                    "overlay": [{"text": "test", "position": "center"}],
                },
            )],
        )
        path = _write_manifest(manifest)
        with pytest.raises(ValueError, match="position"):
            load_manifest(path)

    def test_clip_overlay_missing_text_raises(self):
        manifest = _minimal_manifest(
            sections=[_single_clip_section(
                clip={
                    "path": "/tmp/fake.mp4",
                    "annotation_side": "left",
                    "overlay": [{"position": "top-left"}],
                },
            )],
        )
        path = _write_manifest(manifest)
        with pytest.raises(ValueError, match="text"):
            load_manifest(path)

    def test_clip_overlay_missing_position_raises(self):
        manifest = _minimal_manifest(
            sections=[_single_clip_section(
                clip={
                    "path": "/tmp/fake.mp4",
                    "annotation_side": "left",
                    "overlay": [{"text": "test"}],
                },
            )],
        )
        path = _write_manifest(manifest)
        with pytest.raises(ValueError, match="position"):
            load_manifest(path)

    def test_clip_overlay_valid_rotations_accepted(self):
        for rot in [0, 90, -90]:
            manifest = _minimal_manifest(
                sections=[_single_clip_section(
                    clip={
                        "path": "/tmp/fake.mp4",
                        "annotation_side": "left",
                        "overlay": [
                            {"text": "test", "position": "middle-left", "rotation": rot},
                        ],
                    },
                )],
            )
            path = _write_manifest(manifest)
            load_manifest(path)  # should not raise

    def test_clip_overlay_invalid_rotation_raises(self):
        manifest = _minimal_manifest(
            sections=[_single_clip_section(
                clip={
                    "path": "/tmp/fake.mp4",
                    "annotation_side": "left",
                    "overlay": [
                        {"text": "test", "position": "top-left", "rotation": 45},
                    ],
                },
            )],
        )
        path = _write_manifest(manifest)
        with pytest.raises(ValueError, match="rotation"):
            load_manifest(path)

    def test_clip_overlay_invalid_weight_raises(self):
        manifest = _minimal_manifest(
            sections=[_single_clip_section(
                clip={
                    "path": "/tmp/fake.mp4",
                    "annotation_side": "left",
                    "overlay": [
                        {"text": "test", "position": "top-left", "weight": "italic"},
                    ],
                },
            )],
        )
        path = _write_manifest(manifest)
        with pytest.raises(ValueError, match="weight"):
            load_manifest(path)

    def test_section_overlay_accepted(self):
        manifest = _minimal_manifest(
            sections=[{
                "template": "single_clip",
                "header": "Test",
                "clip": {"path": "/tmp/fake.mp4", "annotation_side": "left"},
                "overlay": [
                    {"text": "DRAFT", "position": "top-right", "color": "#FF0000"},
                ],
            }],
        )
        path = _write_manifest(manifest)
        config = load_manifest(path)
        assert config["sections"][0]["overlay"][0]["text"] == "DRAFT"

    def test_section_overlay_invalid_position_raises(self):
        manifest = _minimal_manifest(
            sections=[{
                "template": "single_clip",
                "header": "Test",
                "clip": {"path": "/tmp/fake.mp4", "annotation_side": "left"},
                "overlay": [{"text": "bad", "position": "invalid"}],
            }],
        )
        path = _write_manifest(manifest)
        with pytest.raises(ValueError, match="position"):
            load_manifest(path)
