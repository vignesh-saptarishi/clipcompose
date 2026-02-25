# clipcompose

Manifest-driven video composition. Spatial layout (9 templates) + temporal assembly (transitions).

## Package Structure

- `src/clipcompose/` — source code
- `tests/` — pytest tests (self-contained, synthetic frames, no real videos needed)
- `examples/` — example YAML manifests (spatial + assembly)
- `docs/design.md` — full specification

## Running Tests

```bash
pytest tests/ -v
```

## Key Modules

| Module | Purpose |
|--------|---------|
| `common.py` | Color parsing, font loading (`CLIPCOMPOSE_FONT` env var), path resolution, clip loading |
| `manifest.py` | YAML manifest validation for spatial composition (all 9 templates) |
| `atoms.py` | AnnotatedClip rendering — video + flush annotation band as one visual unit |
| `overlays.py` | Per-clip and section-level text overlays (9-position grid, rotation) |
| `sections.py` | All 9 section template renderers |
| `cli.py` | Spatial composition CLI entry point |
| `assembly_manifest.py` | YAML manifest validation for temporal assembly |
| `assemble_cli.py` | Native ffmpeg temporal assembly CLI entry point |

## Entry Points

- `clipcompose` → `clipcompose.cli:main`
- `clipcompose-assemble` → `clipcompose.assemble_cli:main`

## Conventions

- **Proportional scaling:** Atom-level constants scale with `bbox_h` relative to `REF_H=900`. Section-level constants scale with output height relative to `_SEC_REF_H=1080`. Every constant has `(value_at_reference, floor)`.
- **Color palette:** Manifests define `colors:` with keys `text`, `text_secondary`, `accent`. Values are hex strings parsed to RGB tuples.
- **Manifest-driven:** All layout, text, and styling declared in YAML. Code is content-agnostic.
- **Fixed grid shapes:** 2x1, 2x2, 3x1, 2x4, 3x4 — not generic NxM.

## Dependencies

- `numpy` — frame arrays
- `Pillow` — text rendering, image composition
- `moviepy>=2.0` — video I/O, compositing
- `PyYAML` — manifest parsing
