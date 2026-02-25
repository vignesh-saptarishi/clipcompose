# clipcompose — Design

Date: February 24, 2026
Status: Implemented

## Overview

A YAML manifest-driven system for composing research companion videos from clips, plots, and text. The compositor is clip-agnostic — it takes mp4 files at declared paths and arranges them into annotated, themed video sections. All text content (captions, outcome labels, descriptions) is specified in the manifest. The compositor renders layout; it does not generate or interpret content.

## Two Composition Axes

**Spatial composition** arranges content within a single frame — clips side by side, text panels, headers, annotations. This is what **templates** do. A template takes a config (which clips, which labels, which colors) and produces a video segment at a fixed resolution.

**Temporal composition** sequences segments over time — one section follows another, with transitions between them. This is what the **assembly pipeline** does. It takes pre-rendered section mp4s and merges them into a final video.

Two-step workflow: render spatial sections independently, then assemble in time. This lets you iterate on one section without re-rendering everything.

```
section manifests → spatial renderers → section mp4s
                                            ↓
assembly manifest → assembly pipeline → final.mp4
```

## Inputs

The compositor consumes mp4 video files at paths declared in the manifest. It does not care how those files were produced — they could come from RL episode rendering, screen recordings, or any other source. All metadata about the clips (outcome, captions, physics parameters) is specified in the manifest, not read from companion files.

## Manifest Structure

A spatial manifest is a YAML file with four top-level blocks:

```yaml
video:       # Resolution, fps, background
paths:       # Named path variables for ${substitution}
colors:      # Named color palette
sections:    # Ordered list of sections, each using a template
```

**Path variables.** String values anywhere in `sections` can use `${name}` syntax, resolved from the `paths:` block. Example: `${videos}/grid1/ep_01.mp4` with `videos: "/data/vids"` resolves to `/data/vids/grid1/ep_01.mp4`.

**Section labels.** Each section supports an optional `label` field — a unique short name used for output filenames. When present, `--render-all` writes `section-NN-label.mp4` instead of `section-NN-template.mp4`. Labels are validated for uniqueness across sections. Using labels makes assembly manifests stable across section reordering or template changes.

**Template files.** `_template.yaml` and `_template-assembly.yaml` in `video-manifests/` document all available fields and templates with examples.

## Color Palette

Colors are defined in the manifest's `colors:` block as a named palette. Templates reference colors by palette key name. Inline hex values (`"#RRGGBB"`) are also accepted.

**Required keys** (used by all templates for UI chrome):

| Key | Role |
|-----|------|
| `text` | Body text, labels |
| `text_secondary` | Muted text, default annotation color |
| `accent` | Section header bars |

**Conventional keys** (semantic roles in this research project):

| Key | Role | Typical value |
|-----|------|---------------|
| `landed` | Successful outcome | `#50DC78` |
| `crashed` | Failed outcome | `#F04646` |

Example:

```yaml
colors:
  accent: "#B1134D"
  text: "#D5D5D3"
  text_secondary: "#888888"
  landed: "#50DC78"
  crashed: "#F04646"
```

## The Atom: AnnotatedClip

The fundamental building block. A clip + annotation band treated as a single rectangular object.

```yaml
clip:
  path: "episode_042.mp4"
  annotation_side: left       # left | right | above | below
  annotations:                # optional — empty list or omitted = no band
    - text: "LANDED"
      color: "#50DC78"
      weight: bold
    - text: " "               # spacer line
    - text: "g=-5.2"
    - text: "autocorr=0.87"
```

**Visual treatment:** Annotation band is flush against the clip edge — no gap. Together they form one rectangle ("unit"). The unit is centered in its bounding box. A thin accent-colored border outlines the unit.

**Annotation band sizing:** Computed from text content. Measure rendered text, add internal padding, clamp to min/max fraction of bbox. The clip fills the remaining space, aspect-ratio-preserved. Band's perpendicular dimension matches the video exactly.

**Annotations list:** Each entry has `text` (required), optional `color` (hex or palette key), optional `weight` ("normal" or "bold"). Bold gets a font size bump. Empty annotations = no band, just centered video.

**Proportional scaling:** All pixel constants (fonts, padding, spacing, border) scale linearly with bbox_h. Reference height is 900px (single-clip content area at 1080p). Each constant has an absolute floor for readability at small sizes (grid cells).

## Section Container

Every template shares the same section container: header bar + subtitle + content area with outer padding.

```
┌─────────────────────────────────────┐
│  outer padding                       │
│  ┌───────────────────────────────┐  │
│  │ ■ Section Header              │  │
│  │   Subtitle text               │  │
│  └───────────────────────────────┘  │
│                                      │
│  ┌─── content area ──────────────┐  │
│  │                                │  │
│  │   (template renders here)     │  │
│  │                                │  │
│  └────────────────────────────────┘  │
│                                      │
│  outer padding                       │
└─────────────────────────────────────┘
```

Section-level sizes (outer padding, title bar height, font sizes, gaps) scale proportionally with output resolution height (ref 1080p). Each constant is a `(value_at_1080, floor)` tuple.

## Templates

Nine template types. All share the section container (header + subtitle + content area) except `title_card` which is full-frame.

---

### title_card

Full-frame static text card. Centered title + optional subtitle on dark background. No header bar, no video clips.

**Accent styling:** A thin full-width accent bar at the top edge of the frame (~4px at 1080p). An accent-colored horizontal underline below the title text (~3px, ~60% frame width, centered), visually separating title from subtitle. Uses `accent` color from the palette.

```
════════════════════════════════════  (accent bar, top edge)
┌──────────────────────────────────┐
│                                  │
│      Latent World Geometry       │
│      ════════════════════  (accent underline)
│      Article 1: What Do...       │
│                                  │
└──────────────────────────────────┘
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `title` | string | yes | Large centered text. Supports `\n` for line breaks. |
| `subtitle` | string | no | Smaller text below title in muted color. |
| `duration` | float | yes | Card duration in seconds. |

```yaml
- template: title_card
  title: "Physics Priors in Latent Space"
  subtitle: "Labeled vs Blind Agent Comparison"
  duration: 3.0
```

---

### single_clip

One AnnotatedClip centered in the content area.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `header` | string | yes | Section header bar text. |
| `subtitle` | string | no | Subtitle below header. |
| `clip` | clip dict | yes | Single clip with `path`, `annotation_side`, optional `annotations`. |

```yaml
- template: single_clip
  header: "Episode 14"
  subtitle: "Labeled agent, g=-4.4"
  clip:
    path: "episode_0014.mp4"
    annotation_side: left
    annotations:
      - text: "LANDED"
        color: "#50DC78"
        weight: bold
      - text: "g=-4.4"
```

---

### grid_2x1

Two clips side by side (2 columns, 1 row). Single-row grids cap cell height to reduce dead space above/below landscape videos.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `header` | string | yes | Section header bar text. |
| `subtitle` | string | no | Subtitle below header. |
| `clips` | list (2) | yes | Exactly 2 clip dicts. |

```yaml
- template: grid_2x1
  header: "Side-by-Side Comparison"
  subtitle: "Labeled vs Blind"
  clips:
    - path: "episode_0014.mp4"
      annotation_side: left
      annotations: [...]
    - path: "episode_0022.mp4"
      annotation_side: left
      annotations: [...]
```

---

### grid_2x2

Four clips in a 2×2 grid (2 columns, 2 rows). Supports optional column headers.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `header` | string | yes | Section header bar text. |
| `subtitle` | string | no | Subtitle below header. |
| `clips` | list (4) | yes | Exactly 4 clip dicts, row-major order. |
| `column_headers` | list (2) | no | Text labels centered above each column. |

```yaml
- template: grid_2x2
  header: "Four Configurations"
  column_headers: ["Labeled", "Blind"]
  clips:
    - path: "ep_01.mp4"
      annotation_side: left
      annotations: [...]
    - path: "ep_02.mp4"
      annotation_side: left
      annotations: [...]
    - path: "ep_03.mp4"
      annotation_side: left
      annotations: [...]
    - path: "ep_04.mp4"
      annotation_side: left
      annotations: [...]
```

---

### grid_3x1

Three clips side by side (3 columns, 1 row). Single-row cell height cap applies.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `header` | string | yes | Section header bar text. |
| `subtitle` | string | no | Subtitle below header. |
| `clips` | list (3) | yes | Exactly 3 clip dicts. |

```yaml
- template: grid_3x1
  header: "Three-Way Comparison"
  clips:
    - path: "ep_01.mp4"
      annotation_side: left
      annotations: [...]
    - path: "ep_02.mp4"
      annotation_side: left
      annotations: [...]
    - path: "ep_03.mp4"
      annotation_side: left
      annotations: [...]
```

---

### grid_2x4

Eight clips in a 2×4 grid (2 columns, 4 rows). Supports optional column headers.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `header` | string | yes | Section header bar text. |
| `subtitle` | string | no | Subtitle below header. |
| `clips` | list (8) | yes | Exactly 8 clip dicts, row-major order. |
| `column_headers` | list (2) | no | Text labels centered above each column. |

```yaml
- template: grid_2x4
  header: "Labeled vs Blind — 4 Episodes Each"
  column_headers: ["Labeled Agent", "Blind Agent"]
  clips:
    - path: "labeled_ep01.mp4"
      annotation_side: left
      annotations: [...]
    # ... 7 more clips (row-major: top-left, top-right, 2nd-left, ...)
```

---

### grid_3x4

Twelve clips in a 3×4 grid (3 columns, 4 rows). Supports optional column headers.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `header` | string | yes | Section header bar text. |
| `subtitle` | string | no | Subtitle below header. |
| `clips` | list (12) | yes | Exactly 12 clip dicts, row-major order. |
| `column_headers` | list (3) | no | Text labels centered above each column. |

```yaml
- template: grid_3x4
  header: "Three Conditions — 4 Episodes Each"
  column_headers: ["Baseline", "Zeroed", "Shuffled"]
  clips:
    - path: "baseline_ep01.mp4"
      annotation_side: left
      annotations: [...]
    # ... 11 more clips (row-major order)
```

---

### paired_2x2

Two groups side by side, each with its own header and a 2×2 sub-grid (8 clips total). A vertical divider separates the groups. The group gap is 3× wider than the cell gap for clear visual separation.

```
┌─ Group A ──────────┐ │ ┌─ Group B ──────────┐
│  Group Header A     │ │ │  Group Header B     │
│ ┌──────┬──┬──────┐ │ │ │ ┌──────┬──┬──────┐ │
│ │ c0   │  │ c1   │ │ │ │ │ c4   │  │ c5   │ │
│ └──────┴──┴──────┘ │ │ │ └──────┴──┴──────┘ │
│ ┌──────┬──┬──────┐ │ │ │ ┌──────┬──┬──────┐ │
│ │ c2   │  │ c3   │ │ │ │ │ c6   │  │ c7   │ │
│ └──────┴──┴──────┘ │ │ │ └──────┴──┴──────┘ │
└────────────────────┘ │ └────────────────────┘
                       divider
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `header` | string | yes | Section header bar text. |
| `subtitle` | string | no | Subtitle below header. |
| `groups` | list (2) | yes | Exactly 2 group dicts. |
| `groups[].header` | string | yes | Group header text (centered above its 2×2 grid). |
| `groups[].clips` | list (4) | yes | Exactly 4 clip dicts per group, row-major order. |

```yaml
- template: paired_2x2
  header: "Labeled vs Blind — 4 Configs Each"
  subtitle: "Left: labeled agent | Right: blind agent"
  groups:
    - header: "Labeled Agent"
      clips:
        - path: "labeled_ep01.mp4"
          annotation_side: above
          annotations:
            - text: "LANDED"
              color: "#50DC78"
              weight: bold
            - text: "g=-4.4"
        - path: "labeled_ep02.mp4"
          annotation_side: above
          annotations: [...]
        - path: "labeled_ep03.mp4"
          annotation_side: above
          annotations: [...]
        - path: "labeled_ep04.mp4"
          annotation_side: above
          annotations: [...]
    - header: "Blind Agent"
      clips:
        - path: "blind_ep01.mp4"
          annotation_side: above
          annotations: [...]
        - path: "blind_ep02.mp4"
          annotation_side: above
          annotations: [...]
        - path: "blind_ep03.mp4"
          annotation_side: above
          annotations: [...]
        - path: "blind_ep04.mp4"
          annotation_side: above
          annotations: [...]
```

---

### text_slide

Static text section — like a presentation slide. 1, 2, or 3 columns with annotation-style line lists. Uses the standard section container (header bar + subtitle). Duration from config.

**Layout:** Columns are equal width. 2+ columns get subtle accent-colored vertical dividers between them (~2px at 1080p, muted accent). Text is vertically centered within each column, left-aligned. For 3 columns, the base font size is reduced (~85% of 1-column size) to maximize text density.

```
┌─────────────────────────────────────┐
│  ■ Section Header                    │
│    Subtitle                          │
├──────────┬──┬──────────┬──┬─────────┤
│          │  │          │  │         │
│  Column  │÷ │  Column  │÷ │ Column  │
│  lines   │  │  lines   │  │  lines  │
│          │  │          │  │         │
└──────────┴──┴──────────┴──┴─────────┘
                (÷ = accent divider)
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `header` | string | yes | Section header bar text. |
| `subtitle` | string | no | Subtitle below header. |
| `duration` | float | yes | Slide duration in seconds. |
| `columns` | list (1–3) | yes | 1 to 3 column dicts, each with a `lines` list. |
| `columns[].lines` | list | yes | Annotation-style `{text, color, weight}` entries. |

```yaml
- template: text_slide
  label: key-findings
  header: "Key Findings"
  subtitle: "Labeled vs Blind Agent"
  duration: 5
  columns:
    - lines:
        - text: "Labeled Agent"
          weight: bold
        - text: "22D observation"
        - text: "Knows physics params"
    - lines:
        - text: "Blind Agent"
          weight: bold
          color: "#e04c77"
        - text: "15D observation"
        - text: "No physics info"
```

---

### Grid behavior (shared across all grid templates)

- **Uniform cell size** — all cells in a grid are the same dimensions.
- **Duration = longest clip** — shorter clips have their last frame frozen.
- **Single-row height cap** — `grid_2x1` and `grid_3x1` cap cell height to `0.75 × cell_w` to reduce dead space around landscape videos.
- **Column headers** — optional for multi-row grids (`grid_2x2`, `grid_2x4`, `grid_3x4`). Centered above each column, rendered in `text_secondary` color.
- **Each clip is an independent atom** — annotation side, annotations, everything is per-clip.

## Clip Behavior

**FPS normalization.** Source clips are resampled to the manifest's target fps on load.

**Duration handling.** In grid templates, duration = longest clip; shorter clips have their last frame frozen. In paired_2x2, same rule applies per group.

**Scaling.** Clips are scaled to fit their allocated cell while preserving aspect ratio, centered within the cell.

**Each clip is an independent atom.** Annotation side, annotations, everything is per-clip. One clip can have left annotations, another above, another none.

## Text Overlays

Semi-transparent text rendered on top of video frames. Works at two levels:

- **Per-clip overlay** — `overlay` field on a clip dict. Rendered within the clip's cell on each video frame.
- **Section-level overlay** — `overlay` field on the section dict. Rendered over the entire composed section frame as a final pass.

### Positioning

A 3x3 grid system with 9 named positions:

```
top-left      top-center      top-right
middle-left   middle-center   middle-right
bottom-left   bottom-center   bottom-right
```

Margin ~5% from edges. Text is drawn on a semi-transparent dark rounded-rect background (~60% opacity black) for readability against any video content.

### Rotation

Optional `rotation` field: `0` (horizontal, default), `90` (reads top-to-bottom), or `-90` (reads bottom-to-top). The entire overlay box (text + background) is rotated around its center before placement. Useful for vertical labels along clip edges.

### Schema

Each overlay is a list of items (multiple overlays at different positions allowed):

```yaml
# Per-clip overlay
clip:
  path: "episode.mp4"
  annotation_side: left
  annotations: [...]
  overlay:
    - text: "g = -4.4"
      position: bottom-left
      color: "#50DC78"        # optional, default: text color
      weight: bold            # optional
      rotation: 0             # optional (0 | 90 | -90)

# Section-level overlay
- template: grid_2x2
  header: "Comparison"
  overlay:
    - text: "Draft — not final"
      position: top-right
      color: "#F04646"
  clips: [...]
```

Font size scales with the target area (clip cell bbox for per-clip, full frame for section-level). Per-clip overlays are rendered per-frame using moviepy's `fl_image`. Section-level overlays are applied after all clips are composed.

## Assembly Pipeline

Temporal composition of pre-rendered sections. Render each spatial section as an mp4, then use a separate assembly manifest to merge them in time with transitions.

### Assembly manifest schema

```yaml
video:
  fps: 30
  transition: 1.5              # global default transition duration (seconds)
  transition_type: fade_to_black  # global default: "crossfade" or "fade_to_black"
paths:
  renders: "/path/to/renders"
sections:
  - path: "${renders}/title-card.mp4"
    transition: 1.5             # per-section override (outgoing transition)
    transition_type: fade_to_black
  - path: "${renders}/grid-3x1.mp4"
    transition: 0.5
    transition_type: crossfade
  - path: "${renders}/paired-2x2.mp4"
    # last section's transition is ignored (nothing follows)
```

### Transition types

- **crossfade** — clips overlap by `transition` seconds with cross-dissolve. Reduces total duration.
- **fade_to_black** — outgoing clip fades out over `transition/2` seconds, incoming clip fades in over `transition/2` seconds. No temporal overlap.
- **hard cut** — set `transition: 0` (type is ignored). No effects, no overlap.

The `transition` field on each section controls the *outgoing* transition — how this section transitions INTO the next one.

### Implementation

The assembly pipeline uses native ffmpeg filter graphs (not moviepy). This avoids frame-by-frame processing and enables GPU encoding.

**Crossfade** boundaries use `xfade=transition=fade` filters — clips overlap by `transition` seconds. Consecutive crossfade clips are chained: `[0:v][1:v]xfade=...[xf1]; [xf1][2:v]xfade=...[xf2]`.

**Fade_to_black** boundaries use per-clip `fade=in`/`fade=out` filters joined with `concat` — no temporal overlap. The outgoing clip fades out over `T/2`, the incoming clip fades in over `T/2`.

Groups of consecutive crossfade-connected clips are assembled with xfade internally, then groups are joined with concat at fade_to_black boundaries.

### CLI workflow

```bash
# Step 1: Render all spatial sections (parallel)
python -m clipcompose.cli \
  --manifest manifest.yaml --output /tmp/renders/ --render-all --workers 4

# Step 1 (single section, for iteration)
python -m clipcompose.cli \
  --manifest manifest.yaml --output /tmp/section.mp4 --section 6

# Step 1 (quick preview — cap each section to 2 seconds)
python -m clipcompose.cli \
  --manifest manifest.yaml --output /tmp/renders/ --render-all --preview-duration 2

# Step 2: Assemble in time
python -m clipcompose.assemble_cli \
  --manifest assembly-manifest.yaml --output final.mp4

# Validate manifests without rendering
python -m clipcompose.cli --manifest manifest.yaml --validate
```

## Output Encoding

Encoding settings are not part of the manifest — the manifest describes content, not output format. Both CLIs support `--gpu` for NVENC hardware encoding (default is CPU/libx264).

| Setting | CPU (default) | GPU (`--gpu`) |
|---------|---------------|---------------|
| Codec | libx264 | h264_nvenc |
| Quality | CRF 20 | CQ 20 |
| Preset | medium | medium |
| Pixel format | yuv420p | yuv420p |
| Audio | none | none |

**NVENC note.** moviepy uses its own bundled ffmpeg binary (`imageio_ffmpeg`) which lacks NVENC support. Both CLIs override this with `os.environ["IMAGEIO_FFMPEG_EXE"] = "/usr/bin/ffmpeg"` to use the system ffmpeg. Consumer GPUs (e.g. 4090) have a ~3 concurrent NVENC session limit — use `--workers 3` with `--gpu`, or use CPU encoding for higher parallelism.

## Validation

**Upfront validation.** Before rendering, the compositor validates the entire manifest: checks all clip paths exist, validates template names, checks required fields per template, and reports errors. Avoids wasting render time on a manifest with typos.

**Path validation.** Separate `--validate` flag on the assembly CLI checks all section mp4 paths exist before assembling.

## Design Decisions

**Spatial layout:**

- One annotation side at a time per clip (no multi-side). Keeps geometry simple.
- Flush edge band — annotation and clip are one visual unit, no gap.
- Unit-centered layout — video + band centered as one tight rectangle.
- Accent border — thin border around each unit.
- Proportional scaling everywhere — atoms scale with bbox_h, sections with output height.
- Fixed grid shapes (not generic NxM) — keeps validation simple and layouts predictable.
- Uniform cell size within a grid. No variable column/row sizes.
- `paired_2x2` uses `groups` list (not flat `clips`) — each group has its own header and exactly 4 clips.

**Temporal assembly:**

- Transitions are assembly-only — section renderers return plain clips with no fade effects.
- Flat sections list with per-section transition overrides over global defaults.
- Native ffmpeg filter graph assembly (not moviepy). Groups consecutive crossfade clips with xfade, joins groups at fade_to_black boundaries with concat. No frame-by-frame processing.
- Same `${var}` path resolution system as spatial manifests.

## Code Structure

```
src/clipcompose/
    __init__.py              # package init
    common.py                # hex color parsing, font loading, path resolution, clip loading
    manifest.py              # spatial manifest: load + validate (all templates, label uniqueness)
    atoms.py                 # AnnotatedClip: measure + render
    overlays.py              # text overlay rendering (per-clip + section-level)
    sections.py              # section renderers: single_clip, title_card, text_slide, grids, paired_2x2
    cli.py                   # spatial manifest → render → export mp4 (--render-all, --workers, --gpu)
    assembly_manifest.py     # assembly manifest: load + validate
    assembly.py              # moviepy-based temporal assembly (alternative to native ffmpeg)
    assemble_cli.py          # assembly manifest → native ffmpeg filter graph → export mp4

examples/
    template-spatial.yaml    # all 9 templates documented with field tables and examples
    template-assembly.yaml   # assembly manifest template with transition types
```

## What This Does NOT Include

- Generic NxM grids (fixed shapes only: 2x1, 2x2, 3x1, 2x4, 3x4)
- Portrait mode
- Audio handling
- Static image template (plots/diagrams — future scope)
