"""Cuts manifest loader — batch video cutting from YAML.

Parses YAML manifests that describe clips to extract from a source video.
Follows the same ${var} path resolution as spatial and assembly manifests.

Cuts manifest schema:
  source: "source.mp4"            # or "${raw}/source.mp4"
  paths:
    raw: "/data/recordings"
  cuts:
    - id: seg-001
      start: 669.0
      end: 937.0
"""

from pathlib import Path

import yaml

from .common import resolve_path_vars


def load_cuts_manifest(manifest_path: str | Path) -> dict:
    """Load, validate, and normalize a cuts manifest.

    Processing pipeline:
      1. Parse YAML.
      2. Resolve ${path} variables in source.
      3. Validate each cut entry (id, start, end).
      4. Check for duplicate ids.

    Args:
        manifest_path: Path to the YAML cuts manifest.

    Returns:
        Normalized config dict with resolved source path and validated cuts.

    Raises:
        ValueError: Missing/invalid fields.
    """
    with open(manifest_path) as f:
        raw = yaml.safe_load(f)

    if "source" not in raw:
        raise ValueError("Cuts manifest: missing required 'source' field")
    if "cuts" not in raw:
        raise ValueError("Cuts manifest: missing required 'cuts' field")

    paths = raw.get("paths", {})
    source = resolve_path_vars(str(raw["source"]), paths)

    cuts = []
    seen_ids = set()
    for i, cut in enumerate(raw["cuts"]):
        if "id" not in cut:
            raise ValueError(f"Cut {i}: missing required field 'id'")
        if "start" not in cut:
            raise ValueError(f"Cut {i}: missing required field 'start'")
        if "end" not in cut:
            raise ValueError(f"Cut {i}: missing required field 'end'")

        start = float(cut["start"])
        end = float(cut["end"])

        if start < 0:
            raise ValueError(f"Cut {i} ({cut['id']}): start must be >= 0, got {start}")
        if start >= end:
            raise ValueError(
                f"Cut {i} ({cut['id']}): start ({start}) must be < end ({end})"
            )

        cid = str(cut["id"])
        if cid in seen_ids:
            raise ValueError(f"Duplicate cut id: '{cid}'")
        seen_ids.add(cid)

        cuts.append({"id": cid, "start": start, "end": end})

    return {"source": source, "cuts": cuts}


def validate_cuts_source(config: dict) -> None:
    """Check that the source video path exists on disk.

    Raises:
        FileNotFoundError: If source file is missing.
    """
    p = Path(config["source"])
    if not p.exists():
        raise FileNotFoundError(f"Source video not found: {config['source']}")
