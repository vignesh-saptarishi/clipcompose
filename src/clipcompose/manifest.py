"""Manifest loader for v3 compositor.

Parses YAML manifests, resolves ${path} variables, converts hex colors
to RGB tuples, validates template names and per-template required fields.

v3 schema differences from v1:
  - Template types: "single_clip", "title_card", "paired_2x2", "grid_2x1", "grid_2x2", "grid_3x1", "grid_2x4", "grid_3x4".
  - Clip fields: annotation_side + annotations list (each with text,
    optional color, optional weight). Matches v1 grid annotation pattern.
  - Stricter validation: annotation_side is enum-checked.
"""

from pathlib import Path

import yaml

from .common import parse_hex_color, resolve_path_vars


# ── Valid templates and their required fields ──────────────────────

VALID_TEMPLATES = {"single_clip", "title_card", "text_slide", "grid_2x1", "grid_2x2", "grid_3x1", "grid_2x4", "grid_3x4", "paired_2x2"}

VALID_ANNOTATION_SIDES = {"left", "right", "above", "below"}

VALID_WEIGHTS = {"normal", "bold"}

VALID_TEXT_SLIDE_ALIGNS = {"left", "center"}

GRID_CLIP_COUNTS = {"grid_2x1": 2, "grid_2x2": 4, "grid_3x1": 3, "grid_2x4": 8, "grid_3x4": 12}

GRID_COL_COUNTS = {"grid_2x1": 2, "grid_2x2": 2, "grid_3x1": 3, "grid_2x4": 2, "grid_3x4": 3}

VALID_OVERLAY_POSITIONS = {
    "top-left", "top-center", "top-right",
    "middle-left", "middle-center", "middle-right",
    "bottom-left", "bottom-center", "bottom-right",
}

VALID_ROTATIONS = {0, 90, -90}


# ── Manifest loading ──────────────────────────────────────────────


def load_manifest(manifest_path: str | Path) -> dict:
    """Load, validate, and normalize a v3 video composition manifest.

    Processing pipeline:
      1. Parse YAML.
      2. Parse video.resolution as tuple, video.background as RGB.
      3. Parse all colors.* hex strings to RGB tuples.
      4. Resolve ${path} variables in all section string values.
      5. Validate template names and per-template required fields.

    Args:
        manifest_path: Path to the YAML manifest file.

    Returns:
        Normalized config dict ready for template dispatch.

    Raises:
        ValueError: Invalid template, missing field, bad annotation_side/status.
        FileNotFoundError: Missing manifest file.
    """
    with open(manifest_path) as f:
        raw = yaml.safe_load(f)

    config = {}

    # Video settings — parse resolution as tuple, background as RGB.
    video = raw["video"]
    video["resolution"] = tuple(video["resolution"])
    video["background"] = parse_hex_color(video["background"])
    config["video"] = video

    # Path variables for ${name} substitution.
    paths = raw.get("paths", {})

    # Colors — parse all hex strings to RGB tuples.
    colors = {}
    for key, value in raw.get("colors", {}).items():
        if isinstance(value, str):
            colors[key] = parse_hex_color(value)
        elif isinstance(value, list):
            colors[key] = tuple(value)
        else:
            colors[key] = value
    config["colors"] = colors

    # Sections — resolve paths, validate template + fields + labels.
    sections = []
    labels_seen = {}
    for i, section in enumerate(raw.get("sections", [])):
        template = section.get("template")
        if template not in VALID_TEMPLATES:
            raise ValueError(
                f"Section {i}: Unknown template '{template}'. "
                f"Valid: {sorted(VALID_TEMPLATES)}"
            )
        resolved = _resolve_section_paths(section, paths)
        _validate_section(resolved, i)

        # Optional label: must be unique across sections.
        label = resolved.get("label")
        if label is not None:
            if not isinstance(label, str) or not label.strip():
                raise ValueError(f"Section {i}: 'label' must be a non-empty string")
            if label in labels_seen:
                raise ValueError(
                    f"Section {i}: duplicate label '{label}' "
                    f"(also used by section {labels_seen[label]})"
                )
            labels_seen[label] = i

        sections.append(resolved)
    config["sections"] = sections

    return config


def _resolve_section_paths(obj, paths: dict):
    """Recursively resolve ${var} in all string values within a section."""
    if isinstance(obj, str):
        return resolve_path_vars(obj, paths)
    elif isinstance(obj, dict):
        return {k: _resolve_section_paths(v, paths) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_resolve_section_paths(item, paths) for item in obj]
    return obj


def _validate_section(section: dict, index: int) -> None:
    """Validate per-template required fields and enum values."""
    template = section["template"]

    if template == "single_clip":
        _validate_single_clip(section, index)
    elif template == "title_card":
        _validate_title_card(section, index)
    elif template == "paired_2x2":
        _validate_paired_2x2(section, index)
    elif template == "text_slide":
        _validate_text_slide(section, index)
    elif template in GRID_CLIP_COUNTS:
        _validate_grid(section, index)

    # Section-level overlay (available on all templates).
    overlay = section.get("overlay")
    if overlay is not None:
        _validate_overlay_list(
            overlay, f"Section {index} ({template})"
        )


def _validate_clip(clip: dict, section_idx: int, clip_idx: int, template: str) -> None:
    """Validate a single clip dict (shared by all templates).

    Required: path, annotation_side.
    Optional: annotations (list of {text, color?, weight?}).
    """
    prefix = f"Section {section_idx} ({template}), clip {clip_idx}"

    if "path" not in clip:
        raise ValueError(f"{prefix}: missing required field 'path'")

    if "annotation_side" not in clip:
        raise ValueError(f"{prefix}: missing required field 'annotation_side'")

    side = clip["annotation_side"]
    if side not in VALID_ANNOTATION_SIDES:
        raise ValueError(
            f"{prefix}: invalid annotation_side '{side}'. "
            f"Valid: {sorted(VALID_ANNOTATION_SIDES)}"
        )

    annotations = clip.get("annotations", [])
    if not isinstance(annotations, list):
        raise ValueError(f"{prefix}: 'annotations' must be a list")
    for j, annot in enumerate(annotations):
        if "text" not in annot:
            raise ValueError(f"{prefix}: annotation {j} missing 'text'")
        weight = annot.get("weight")
        if weight is not None and weight not in VALID_WEIGHTS:
            raise ValueError(
                f"{prefix}: annotation {j} invalid weight '{weight}'. "
                f"Valid: {sorted(VALID_WEIGHTS)}"
            )

    overlay = clip.get("overlay")
    if overlay is not None:
        _validate_overlay_list(overlay, prefix)


def _validate_overlay_list(overlay: list, prefix: str) -> None:
    """Validate a list of overlay items.

    Each overlay item: text (required), position (required),
    optional color, weight, rotation.
    """
    if not isinstance(overlay, list):
        raise ValueError(f"{prefix}: 'overlay' must be a list")

    for j, item in enumerate(overlay):
        item_prefix = f"{prefix}, overlay {j}"

        if "text" not in item:
            raise ValueError(f"{item_prefix}: missing 'text'")

        if "position" not in item:
            raise ValueError(f"{item_prefix}: missing 'position'")

        pos = item["position"]
        if pos not in VALID_OVERLAY_POSITIONS:
            raise ValueError(
                f"{item_prefix}: invalid position '{pos}'. "
                f"Valid: {sorted(VALID_OVERLAY_POSITIONS)}"
            )

        weight = item.get("weight")
        if weight is not None and weight not in VALID_WEIGHTS:
            raise ValueError(
                f"{item_prefix}: invalid weight '{weight}'. "
                f"Valid: {sorted(VALID_WEIGHTS)}"
            )

        rotation = item.get("rotation")
        if rotation is not None and rotation not in VALID_ROTATIONS:
            raise ValueError(
                f"{item_prefix}: invalid rotation {rotation}. "
                f"Valid: {sorted(VALID_ROTATIONS)}"
            )


def _validate_single_clip(section: dict, index: int) -> None:
    """Validate a single_clip section."""
    if "clip" not in section:
        raise ValueError(
            f"Section {index} (single_clip): missing required field 'clip'"
        )
    _validate_clip(section["clip"], index, 0, "single_clip")


def _validate_title_card(section: dict, index: int) -> None:
    """Validate a title_card section.

    Required: title (str), duration (positive number).
    Optional: subtitle (str).
    """
    if "title" not in section:
        raise ValueError(
            f"Section {index} (title_card): missing required field 'title'"
        )

    if "duration" not in section:
        raise ValueError(
            f"Section {index} (title_card): missing required field 'duration'"
        )

    dur = section["duration"]
    if not isinstance(dur, (int, float)) or dur <= 0:
        raise ValueError(
            f"Section {index} (title_card): duration must be a positive number, "
            f"got {dur!r}"
        )


def _validate_text_slide(section: dict, index: int) -> None:
    """Validate a text_slide section.

    Required: header (str), duration (positive number), columns (list of 1-3).
    Each column: lines (list of annotation-style dicts with text, optional color/weight).
    """
    template = "text_slide"

    if "duration" not in section:
        raise ValueError(
            f"Section {index} ({template}): missing required field 'duration'"
        )
    dur = section["duration"]
    if not isinstance(dur, (int, float)) or dur <= 0:
        raise ValueError(
            f"Section {index} ({template}): duration must be a positive number, "
            f"got {dur!r}"
        )

    if "columns" not in section:
        raise ValueError(
            f"Section {index} ({template}): missing required field 'columns'"
        )

    columns = section["columns"]
    if not isinstance(columns, list) or not (1 <= len(columns) <= 3):
        n = len(columns) if isinstance(columns, list) else "non-list"
        raise ValueError(
            f"Section {index} ({template}): requires 1 to 3 columns, got {n}"
        )

    for c_idx, col in enumerate(columns):
        prefix = f"Section {index} ({template}), column {c_idx}"

        if "lines" not in col:
            raise ValueError(f"{prefix}: missing required field 'lines'")

        lines = col["lines"]
        if not isinstance(lines, list):
            raise ValueError(f"{prefix}: 'lines' must be a list")

        for l_idx, line in enumerate(lines):
            if "text" not in line:
                raise ValueError(f"{prefix}, line {l_idx}: missing 'text'")
            weight = line.get("weight")
            if weight is not None and weight not in VALID_WEIGHTS:
                raise ValueError(
                    f"{prefix}, line {l_idx}: invalid weight '{weight}'. "
                    f"Valid: {sorted(VALID_WEIGHTS)}"
                )

        align = col.get("align")
        if align is not None and align not in VALID_TEXT_SLIDE_ALIGNS:
            raise ValueError(
                f"{prefix}: invalid align '{align}'. "
                f"Valid: {sorted(VALID_TEXT_SLIDE_ALIGNS)}"
            )


def _validate_grid(section: dict, index: int) -> None:
    """Validate a grid section (grid_2x1 or grid_2x2)."""
    template = section["template"]
    expected = GRID_CLIP_COUNTS[template]

    if "clips" not in section:
        raise ValueError(
            f"Section {index} ({template}): missing required field 'clips'"
        )

    clips = section["clips"]
    if not isinstance(clips, list) or len(clips) != expected:
        raise ValueError(
            f"Section {index} ({template}): requires exactly "
            f"{expected} clips, got {len(clips) if isinstance(clips, list) else 'non-list'}"
        )

    for j, clip in enumerate(clips):
        _validate_clip(clip, index, j, template)

    # Optional column_headers: if present, must be a list of strings
    # with length == number of columns for this grid template.
    column_headers = section.get("column_headers")
    if column_headers is not None:
        expected_cols = GRID_COL_COUNTS[template]
        if not isinstance(column_headers, list):
            raise ValueError(
                f"Section {index} ({template}): 'column_headers' must be a list"
            )
        if len(column_headers) != expected_cols:
            raise ValueError(
                f"Section {index} ({template}): column_headers requires exactly "
                f"{expected_cols} items (one per column), got {len(column_headers)}"
            )
        for j, hdr in enumerate(column_headers):
            if not isinstance(hdr, str):
                raise ValueError(
                    f"Section {index} ({template}): column_headers[{j}] must be a string"
                )


def _validate_paired_2x2(section: dict, index: int) -> None:
    """Validate a paired_2x2 section.

    Required: groups (list of exactly 2 group dicts).
    Each group must have: header (str), clips (list of exactly 4 clip dicts).
    """
    template = "paired_2x2"

    if "groups" not in section:
        raise ValueError(
            f"Section {index} ({template}): missing required field 'groups'"
        )

    groups = section["groups"]
    if not isinstance(groups, list) or len(groups) != 2:
        raise ValueError(
            f"Section {index} ({template}): requires exactly 2 groups, "
            f"got {len(groups) if isinstance(groups, list) else 'non-list'}"
        )

    for g_idx, group in enumerate(groups):
        g_prefix = f"Section {index} ({template}), group {g_idx}"

        if "header" not in group:
            raise ValueError(f"{g_prefix}: missing required field 'header'")

        if "clips" not in group:
            raise ValueError(f"{g_prefix}: missing required field 'clips'")

        clips = group["clips"]
        if not isinstance(clips, list) or len(clips) != 4:
            raise ValueError(
                f"{g_prefix}: requires exactly 4 clips, "
                f"got {len(clips) if isinstance(clips, list) else 'non-list'}"
            )

        for c_idx, clip in enumerate(clips):
            _validate_clip(clip, index, c_idx, f"{template} group {g_idx}")


# ── Path validation ───────────────────────────────────────────────


def validate_paths(config: dict) -> None:
    """Check that all clip/image paths in the manifest exist on disk.

    Walks all sections recursively, finds string values that look like
    file paths (contain '/' and end with a media extension), checks each
    one exists. Reports all missing paths at once.

    Raises:
        FileNotFoundError: Lists all missing files.
    """
    missing = []
    media_extensions = {".mp4", ".png", ".jpg", ".jpeg", ".webp"}

    def _check(obj):
        if isinstance(obj, str):
            p = Path(obj)
            if p.suffix.lower() in media_extensions and "/" in obj:
                if not p.exists():
                    missing.append(obj)
        elif isinstance(obj, dict):
            for v in obj.values():
                _check(v)
        elif isinstance(obj, list):
            for item in obj:
                _check(item)

    for section in config["sections"]:
        _check(section)

    if missing:
        msg = f"Missing {len(missing)} file(s):\n"
        for p in missing:
            msg += f"  - {p}\n"
        raise FileNotFoundError(msg)
