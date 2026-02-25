"""Tests for assembly manifest loader."""

import tempfile

import pytest
import yaml

from clipcompose.assembly_manifest import (
    load_assembly_manifest,
    VALID_TRANSITION_TYPES,
)


def _write_manifest(content: dict) -> str:
    """Write a manifest dict to a temp YAML file, return path."""
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
    yaml.dump(content, f)
    f.close()
    return f.name


def _minimal_assembly(**overrides):
    """Return a minimal valid assembly manifest dict."""
    m = {
        "video": {
            "fps": 30,
            "transition": 0.5,
        },
        "sections": [],
    }
    m.update(overrides)
    return m


def _section(**overrides):
    """Return a minimal valid assembly section."""
    s = {"path": "/tmp/fake.mp4"}
    s.update(overrides)
    return s


class TestLoadAssemblyManifest:
    def test_parses_fps(self):
        path = _write_manifest(_minimal_assembly())
        config = load_assembly_manifest(path)
        assert config["video"]["fps"] == 30

    def test_default_transition(self):
        path = _write_manifest(_minimal_assembly())
        config = load_assembly_manifest(path)
        assert config["video"]["transition"] == 0.5

    def test_default_transition_type_is_crossfade(self):
        path = _write_manifest(_minimal_assembly())
        config = load_assembly_manifest(path)
        assert config["video"]["transition_type"] == "crossfade"

    def test_explicit_transition_type(self):
        m = _minimal_assembly()
        m["video"]["transition_type"] = "fade_to_black"
        path = _write_manifest(m)
        config = load_assembly_manifest(path)
        assert config["video"]["transition_type"] == "fade_to_black"

    def test_resolves_path_variables(self):
        m = _minimal_assembly(
            paths={"renders": "/data/renders"},
            sections=[{"path": "${renders}/section.mp4"}],
        )
        path = _write_manifest(m)
        config = load_assembly_manifest(path)
        assert config["sections"][0]["path"] == "/data/renders/section.mp4"

    def test_section_inherits_global_defaults(self):
        m = _minimal_assembly(sections=[_section()])
        path = _write_manifest(m)
        config = load_assembly_manifest(path)
        sec = config["sections"][0]
        assert sec["transition"] == 0.5
        assert sec["transition_type"] == "crossfade"

    def test_section_overrides_transition(self):
        m = _minimal_assembly(sections=[_section(transition=0)])
        path = _write_manifest(m)
        config = load_assembly_manifest(path)
        assert config["sections"][0]["transition"] == 0

    def test_section_overrides_transition_type(self):
        m = _minimal_assembly(
            sections=[_section(transition_type="fade_to_black")],
        )
        path = _write_manifest(m)
        config = load_assembly_manifest(path)
        assert config["sections"][0]["transition_type"] == "fade_to_black"


class TestAssemblyManifestValidation:
    def test_missing_video_raises(self):
        path = _write_manifest({"sections": []})
        with pytest.raises(ValueError, match="video"):
            load_assembly_manifest(path)

    def test_missing_fps_raises(self):
        m = {"video": {"transition": 0.5}, "sections": []}
        path = _write_manifest(m)
        with pytest.raises(ValueError, match="fps"):
            load_assembly_manifest(path)

    def test_missing_transition_raises(self):
        m = {"video": {"fps": 30}, "sections": []}
        path = _write_manifest(m)
        with pytest.raises(ValueError, match="transition"):
            load_assembly_manifest(path)

    def test_negative_transition_raises(self):
        m = _minimal_assembly()
        m["video"]["transition"] = -1
        path = _write_manifest(m)
        with pytest.raises(ValueError, match="transition"):
            load_assembly_manifest(path)

    def test_invalid_transition_type_raises(self):
        m = _minimal_assembly()
        m["video"]["transition_type"] = "wipe"
        path = _write_manifest(m)
        with pytest.raises(ValueError, match="transition_type"):
            load_assembly_manifest(path)

    def test_section_missing_path_raises(self):
        m = _minimal_assembly(sections=[{}])
        path = _write_manifest(m)
        with pytest.raises(ValueError, match="path"):
            load_assembly_manifest(path)

    def test_section_negative_transition_raises(self):
        m = _minimal_assembly(sections=[_section(transition=-0.5)])
        path = _write_manifest(m)
        with pytest.raises(ValueError, match="transition"):
            load_assembly_manifest(path)

    def test_section_invalid_transition_type_raises(self):
        m = _minimal_assembly(
            sections=[_section(transition_type="dissolve")],
        )
        path = _write_manifest(m)
        with pytest.raises(ValueError, match="transition_type"):
            load_assembly_manifest(path)
