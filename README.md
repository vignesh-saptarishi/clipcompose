# clipcompose

Manifest-driven video composition. Arrange annotated clips into themed sections and assemble them with transitions — all declared in YAML.

**Two composition axes:**

- **Spatial** — 9 template types (title cards, grids, text slides, paired groups) with annotated clips, color palettes, and text overlays. Renders sections to mp4.
- **Temporal** — sequence sections with crossfade, fade-to-black, or hard-cut transitions using native ffmpeg filter graphs.

**Status:** Functional, not yet packaged. See `docs/design.md` for the full specification.
