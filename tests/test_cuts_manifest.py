"""Tests for cuts manifest loader."""

import tempfile

import pytest
import yaml


def _write_manifest(content: dict) -> str:
    """Write a manifest dict to a temp YAML file, return path."""
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
    yaml.dump(content, f)
    f.close()
    return f.name


def _minimal_cuts(**overrides):
    """Return a minimal valid cuts manifest dict."""
    m = {
        "source": "/fake/source.mp4",
        "cuts": [],
    }
    m.update(overrides)
    return m


def _cut(**overrides):
    """Return a minimal valid cut entry."""
    c = {"id": "seg-001", "start": 10.0, "end": 20.0}
    c.update(overrides)
    return c


class TestLoadCutsManifest:
    def test_parses_source(self):
        from clipcompose.cuts_manifest import load_cuts_manifest

        path = _write_manifest(_minimal_cuts())
        config = load_cuts_manifest(path)
        assert config["source"] == "/fake/source.mp4"

    def test_parses_cuts(self):
        from clipcompose.cuts_manifest import load_cuts_manifest

        m = _minimal_cuts(cuts=[_cut()])
        path = _write_manifest(m)
        config = load_cuts_manifest(path)
        assert len(config["cuts"]) == 1
        assert config["cuts"][0]["id"] == "seg-001"
        assert config["cuts"][0]["start"] == 10.0
        assert config["cuts"][0]["end"] == 20.0

    def test_resolves_path_variables_in_source(self):
        from clipcompose.cuts_manifest import load_cuts_manifest

        m = _minimal_cuts(
            source="${raw}/lecture.mp4",
            paths={"raw": "/data/recordings"},
        )
        path = _write_manifest(m)
        config = load_cuts_manifest(path)
        assert config["source"] == "/data/recordings/lecture.mp4"

    def test_multiple_cuts(self):
        from clipcompose.cuts_manifest import load_cuts_manifest

        m = _minimal_cuts(cuts=[
            _cut(id="seg-001", start=10.0, end=20.0),
            _cut(id="seg-002", start=30.0, end=40.0),
        ])
        path = _write_manifest(m)
        config = load_cuts_manifest(path)
        assert len(config["cuts"]) == 2
        assert config["cuts"][1]["id"] == "seg-002"


class TestCutsManifestValidation:
    def test_missing_source_raises(self):
        from clipcompose.cuts_manifest import load_cuts_manifest

        path = _write_manifest({"cuts": []})
        with pytest.raises(ValueError, match="source"):
            load_cuts_manifest(path)

    def test_missing_cuts_raises(self):
        from clipcompose.cuts_manifest import load_cuts_manifest

        path = _write_manifest({"source": "/fake.mp4"})
        with pytest.raises(ValueError, match="cuts"):
            load_cuts_manifest(path)

    def test_cut_missing_id_raises(self):
        from clipcompose.cuts_manifest import load_cuts_manifest

        m = _minimal_cuts(cuts=[{"start": 10.0, "end": 20.0}])
        path = _write_manifest(m)
        with pytest.raises(ValueError, match="id"):
            load_cuts_manifest(path)

    def test_cut_missing_start_raises(self):
        from clipcompose.cuts_manifest import load_cuts_manifest

        m = _minimal_cuts(cuts=[{"id": "seg", "end": 20.0}])
        path = _write_manifest(m)
        with pytest.raises(ValueError, match="start"):
            load_cuts_manifest(path)

    def test_cut_missing_end_raises(self):
        from clipcompose.cuts_manifest import load_cuts_manifest

        m = _minimal_cuts(cuts=[{"id": "seg", "start": 10.0}])
        path = _write_manifest(m)
        with pytest.raises(ValueError, match="end"):
            load_cuts_manifest(path)

    def test_start_after_end_raises(self):
        from clipcompose.cuts_manifest import load_cuts_manifest

        m = _minimal_cuts(cuts=[_cut(start=30.0, end=20.0)])
        path = _write_manifest(m)
        with pytest.raises(ValueError, match="start.*end"):
            load_cuts_manifest(path)

    def test_negative_start_raises(self):
        from clipcompose.cuts_manifest import load_cuts_manifest

        m = _minimal_cuts(cuts=[_cut(start=-1.0)])
        path = _write_manifest(m)
        with pytest.raises(ValueError, match="start"):
            load_cuts_manifest(path)

    def test_duplicate_ids_raises(self):
        from clipcompose.cuts_manifest import load_cuts_manifest

        m = _minimal_cuts(cuts=[
            _cut(id="dup", start=0.0, end=10.0),
            _cut(id="dup", start=20.0, end=30.0),
        ])
        path = _write_manifest(m)
        with pytest.raises(ValueError, match="[Dd]uplicate"):
            load_cuts_manifest(path)


class TestValidateCutsSource:
    def test_existing_source_passes(self, tmp_path):
        from clipcompose.cuts_manifest import validate_cuts_source

        src = tmp_path / "video.mp4"
        src.write_text("fake")
        validate_cuts_source({"source": str(src)})  # should not raise

    def test_missing_source_raises(self):
        from clipcompose.cuts_manifest import validate_cuts_source

        with pytest.raises(FileNotFoundError, match="not found"):
            validate_cuts_source({"source": "/nonexistent/video.mp4"})
