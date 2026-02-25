# clipcompose

Manifest-driven video composition for research and presentation videos.

clipcompose works in two stages:

1. **Spatial composition** — arrange annotated video clips into themed sections using 9 layout templates (grids, paired comparisons, title cards, text slides).
2. **Temporal assembly** — sequence rendered sections into a final video with crossfade, fade-to-black, or hard-cut transitions.

All layout, text, and styling is declared in YAML manifests. The tool is content-agnostic — it works with any video domain.

## Install

```bash
pip install .

# With dev dependencies (pytest):
pip install -e ".[dev]"
```

Requires Python >= 3.10.

## Quick Start

Create a manifest (`manifest.yaml`):

```yaml
video:
  resolution: [1920, 1080]
  fps: 30
  background: "#1A1A1A"

colors:
  text: "#D5D5D3"
  text_secondary: "#888888"
  accent: "#B1134D"

sections:

  - template: single_clip
    header: "Example Section"
    clip:
      path: /path/to/video.mp4
      annotation_side: left
      annotations:

        - text: "Label"
          weight: bold
```

Render it:

```bash
clipcompose --manifest manifest.yaml --output section.mp4 --section 0
```

## Templates

| Template | Description |
|----------|-------------|
| `title_card` | Full-frame centered text with optional subtitle |
| `text_slide` | 1-3 columns of styled text lines |
| `single_clip` | One annotated video clip |
| `grid_2x1` | Two clips side by side |
| `grid_2x2` | Four clips in a 2x2 grid |
| `grid_3x1` | Three clips side by side |
| `grid_2x4` | Eight clips in 2 columns x 4 rows |
| `grid_3x4` | Twelve clips in 3 columns x 4 rows |
| `paired_2x2` | Two labeled 2x2 groups side by side |

## CLI Reference

### clipcompose (spatial composition)

```bash
clipcompose --manifest manifest.yaml --output out.mp4 --section 0
clipcompose --manifest manifest.yaml --output renders/ --render-all
clipcompose --manifest manifest.yaml --output renders/ --render-all --workers 4
clipcompose --manifest manifest.yaml --output out.mp4 --preview-duration 2
clipcompose --manifest manifest.yaml --validate
clipcompose --manifest manifest.yaml --output out.mp4 --gpu
```

### clipcompose-assemble (temporal assembly)

```bash
clipcompose-assemble --manifest assembly.yaml --output final.mp4
clipcompose-assemble --manifest assembly.yaml --output final.mp4 --gpu
```

## Requirements

- **Python >= 3.10**
- **ffmpeg** — system install, needed for assembly CLI and GPU encoding (`--gpu`)
- **Inter font** (optional) — for best text rendering. Falls back to DejaVu Sans, then Pillow default. Override with `CLIPCOMPOSE_FONT` env var.

## Documentation

See `docs/design.md` for the full specification: template schemas, scaling model, assembly pipeline, and design decisions.

Example manifests in `examples/`.

## License

MIT
