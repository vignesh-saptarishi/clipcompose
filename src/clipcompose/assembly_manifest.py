"""Assembly manifest loader — temporal composition of pre-rendered sections.

Parses YAML manifests that describe which mp4 section files to merge,
in what order, with what transitions. Separate from the spatial compositor
manifests (manifest.py) which describe individual section layout.

Assembly manifest schema:
  video:
    fps: 30
    transition: 0.5             # global default crossfade duration
    transition_type: crossfade  # global default: "crossfade" or "fade_to_black"
  paths:
    renders: "/path/to/renders"
  sections:
    - path: "${renders}/title.mp4"
      transition: 0               # per-section override
      transition_type: crossfade  # per-section override
"""

from pathlib import Path

import yaml

from .common import resolve_path_vars


VALID_TRANSITION_TYPES = {"crossfade", "fade_to_black"}


def load_assembly_manifest(manifest_path: str | Path) -> dict:
    """Load, validate, and normalize an assembly manifest.

    Processing pipeline:
      1. Parse YAML.
      2. Validate video settings (fps, transition, transition_type).
      3. Resolve ${path} variables in section paths.
      4. Apply global defaults to each section (transition, transition_type).
      5. Validate per-section fields.

    Args:
        manifest_path: Path to the YAML assembly manifest.

    Returns:
        Normalized config dict with resolved paths and applied defaults.

    Raises:
        ValueError: Missing/invalid fields.
    """
    with open(manifest_path) as f:
        raw = yaml.safe_load(f)

    # Validate top-level video settings.
    if "video" not in raw:
        raise ValueError("Assembly manifest: missing required 'video' section")

    video = raw["video"]
    if "fps" not in video:
        raise ValueError("Assembly manifest: video.fps is required")
    if "transition" not in video:
        raise ValueError("Assembly manifest: video.transition is required")

    default_transition = video["transition"]
    if not isinstance(default_transition, (int, float)) or default_transition < 0:
        raise ValueError(
            f"Assembly manifest: video.transition must be >= 0, got {default_transition!r}"
        )

    default_type = video.get("transition_type", "crossfade")
    if default_type not in VALID_TRANSITION_TYPES:
        raise ValueError(
            f"Assembly manifest: invalid video.transition_type '{default_type}'. "
            f"Valid: {sorted(VALID_TRANSITION_TYPES)}"
        )
    video["transition_type"] = default_type

    config = {"video": video}

    # Path variables for ${name} substitution.
    paths = raw.get("paths", {})

    # Process sections — resolve paths, apply defaults, validate.
    sections = []
    for i, section in enumerate(raw.get("sections", [])):
        # Resolve ${var} in path.
        if "path" not in section:
            raise ValueError(f"Assembly section {i}: missing required field 'path'")
        section["path"] = resolve_path_vars(section["path"], paths)

        # Apply global defaults where section doesn't override.
        if "transition" not in section:
            section["transition"] = default_transition
        else:
            t = section["transition"]
            if not isinstance(t, (int, float)) or t < 0:
                raise ValueError(
                    f"Assembly section {i}: transition must be >= 0, got {t!r}"
                )

        if "transition_type" not in section:
            section["transition_type"] = default_type
        else:
            st = section["transition_type"]
            if st not in VALID_TRANSITION_TYPES:
                raise ValueError(
                    f"Assembly section {i}: invalid transition_type '{st}'. "
                    f"Valid: {sorted(VALID_TRANSITION_TYPES)}"
                )

        sections.append(section)

    config["sections"] = sections
    return config


def validate_assembly_paths(config: dict) -> None:
    """Check that all section mp4 paths exist on disk.

    Raises:
        FileNotFoundError: Lists all missing files.
    """
    missing = []
    for section in config["sections"]:
        p = Path(section["path"])
        if not p.exists():
            missing.append(section["path"])

    if missing:
        msg = f"Missing {len(missing)} section file(s):\n"
        for p in missing:
            msg += f"  - {p}\n"
        raise FileNotFoundError(msg)
