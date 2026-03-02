"""CLI for spatial composition.

Reads a YAML manifest, validates all media paths, renders each section
using the appropriate template, and exports as mp4.

Usage:
    # Render a single section
    python -m clipcompose.cli \
        --manifest manifest.yaml --output /tmp/section.mp4 --section 6

    # Render all sections to a directory (one mp4 per section)
    python -m clipcompose.cli \
        --manifest manifest.yaml --output /tmp/renders/ --render-all

    # Parallel render (4 workers)
    python -m clipcompose.cli \
        --manifest manifest.yaml --output /tmp/renders/ --render-all \
        --workers 4 --preview-duration 2

    # Validate only (no rendering)
    python -m clipcompose.cli \
        --manifest manifest.yaml --validate
"""

import argparse
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from .manifest import load_manifest, validate_paths
from .overlays import apply_overlays_to_frame
from .sections import (
    render_single_clip,
    render_title_card,
    render_text_slide,
    render_grid_2x1, render_grid_2x2,
    render_grid_3x1, render_grid_2x4, render_grid_3x4,
    render_paired_2x2,
    _section_layout,
    render_section_header_frame,
)


# ── Template dispatch ─────────────────────────────────────────────
# Maps template name → renderer function. All renderers share the
# signature: (config, video_settings, colors) -> CompositeVideoClip.

TEMPLATE_RENDERERS = {
    "single_clip": render_single_clip,
    "title_card": render_title_card,
    "text_slide": render_text_slide,
    "grid_2x1": render_grid_2x1,
    "grid_2x2": render_grid_2x2,
    "grid_3x1": render_grid_3x1,
    "grid_2x4": render_grid_2x4,
    "grid_3x4": render_grid_3x4,
    "paired_2x2": render_paired_2x2,
}


# ── Rendering helpers ─────────────────────────────────────────────


def _render_section(section_config, video_settings, colors, preview_duration):
    """Render one section and optionally cap its duration."""
    template = section_config["template"]
    renderer = TEMPLATE_RENDERERS[template]
    clip = renderer(section_config, video_settings, colors)
    if preview_duration and clip.duration > preview_duration:
        clip = clip.subclipped(0, preview_duration)

    # Apply section-level overlays if present.
    overlay_items = section_config.get("overlay")
    if overlay_items:
        resolution = video_settings["resolution"]
        w, h = resolution
        overlay_font_size = max(12, round(24 * h / 1080))

        # Compute the content area region (below header, inside outer padding).
        # title_card has no header/content split — use full frame.
        overlay_region = None
        if template != "title_card":
            sl = _section_layout(h)
            header_frame = render_section_header_frame(
                title=section_config.get("header", ""),
                resolution=resolution,
                bg_color=video_settings["background"],
                colors=colors,
                subtitle=section_config.get("subtitle"),
            )
            header_h = header_frame.shape[0]
            outer_pad = sl["outer_padding"]
            content_y = header_h + sl["header_content_gap"]
            overlay_region = (
                outer_pad,
                content_y,
                w - 2 * outer_pad,
                h - content_y - outer_pad,
            )

        def _apply_overlay(get_frame, t):
            return apply_overlays_to_frame(
                get_frame(t), overlay_items, colors, overlay_font_size,
                region=overlay_region,
            )

        clip = clip.transform(_apply_overlay)

    return clip


def _export_clip(clip, output_path, fps, quiet=False):
    """Write a clip to mp4 with standard encoding settings."""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    clip.write_videofile(
        str(output_path),
        fps=fps,
        codec="libx264",
        audio=False,
        preset="medium",
        ffmpeg_params=["-crf", "20", "-pix_fmt", "yuv420p"],
        logger=None if quiet else "bar",
    )


def _section_filename(index, section_config):
    """Generate a filename for a section.

    Uses label if present (section-NN-label.mp4), otherwise falls back
    to template name (section-NN-template.mp4).
    """
    name = section_config.get("label") or section_config["template"]
    return f"section-{index:02d}-{name}.mp4"


def _render_and_export_one(args):
    """Worker function for parallel rendering.

    Takes a single tuple so it works with ProcessPoolExecutor.map().
    Each worker renders one section and writes it to disk independently.
    The quiet flag suppresses moviepy's progress bar to avoid interleaved
    output from multiple workers.
    """
    index, section_config, video_settings, colors, preview_duration, output_path, fps, quiet = args
    template = section_config["template"]
    header = (section_config.get("header") or section_config.get("title", "")).replace("\n", " ")
    subtitle = (section_config.get("subtitle") or "").replace("\n", " ")
    name = f"{header} / {subtitle}" if header and subtitle else header or subtitle
    label = f"[{index}] {template} — {name}"

    print(f"  START  {label}", flush=True)
    t0 = time.monotonic()
    clip = _render_section(section_config, video_settings, colors, preview_duration)
    _export_clip(clip, output_path, fps, quiet=quiet)
    elapsed = time.monotonic() - t0
    print(f"  DONE   {label} — {clip.duration:.1f}s video, {elapsed:.1f}s wall", flush=True)
    return index, label, clip.duration, str(output_path)


# ── Main composition ─────────────────────────────────────────────


def compose(
    manifest_path: str,
    output_path: str,
    section_index: int | None = None,
    render_all: bool = False,
    preview_duration: float | None = None,
    workers: int = 1,
) -> None:
    """Load manifest, validate, render section(s), export mp4(s).

    Three modes:
      - --section N: render one section to output_path.
      - --render-all: render every section to output_path directory,
        one mp4 per section (section-00-template.mp4, etc.).
      - Neither: render all sections, export only the last one to
        output_path (legacy behavior).

    Args:
        manifest_path: Path to YAML manifest.
        output_path: Output mp4 path, or directory for --render-all.
        section_index: If set, render only this section (0-indexed).
        render_all: If True, output_path is a directory; each section
            gets its own mp4.
        preview_duration: If set, cap each section to this many seconds.
        workers: Number of parallel worker processes for --render-all.
            1 = sequential, >1 = parallel via ProcessPoolExecutor.
    """
    config = load_manifest(manifest_path)
    validate_paths(config)

    video_settings = config["video"]
    colors = config["colors"]
    resolution = video_settings["resolution"]
    fps = video_settings["fps"]

    sections = config["sections"]
    if not sections:
        print("No sections to render.")
        return

    # ── Single section mode ──────────────────────────────────────
    if section_index is not None:
        if section_index < 0 or section_index >= len(sections):
            raise ValueError(
                f"--section {section_index} out of range "
                f"(manifest has {len(sections)} sections, 0-{len(sections)-1})"
            )
        sc = sections[section_index]
        template = sc["template"]
        header = sc.get("header") or sc.get("title", "")
        print(f"Rendering section {section_index}: {template} — {header}")

        clip = _render_section(sc, video_settings, colors, preview_duration)
        print(f"  Duration: {clip.duration:.1f}s")
        print(f"\nResolution: {resolution[0]}x{resolution[1]}, {fps}fps")
        print(f"Writing to: {output_path}")
        _export_clip(clip, output_path, fps)
        print(f"\nDone: {output_path}")
        return

    # ── Render-all mode ──────────────────────────────────────────
    if render_all:
        out_dir = Path(output_path)
        out_dir.mkdir(parents=True, exist_ok=True)

        effective_workers = min(workers, len(sections))
        parallel = effective_workers > 1

        # Build work items — quiet=True in parallel mode to suppress
        # moviepy progress bars that interleave across workers.
        work = []
        for i, sc in enumerate(sections):
            fpath = str(out_dir / _section_filename(i, sc))
            work.append((i, sc, video_settings, colors, preview_duration, fpath, fps, parallel))

        t_start = time.monotonic()

        if not parallel:
            print(f"Rendering {len(sections)} sections to {out_dir}/\n")
            for item in work:
                _render_and_export_one(item)
        else:
            print(
                f"Rendering {len(sections)} sections to {out_dir}/ "
                f"({effective_workers} workers)\n"
            )
            with ProcessPoolExecutor(max_workers=effective_workers) as pool:
                futures = {
                    pool.submit(_render_and_export_one, item): item[0]
                    for item in work
                }
                for future in as_completed(futures):
                    future.result()  # propagate exceptions

        total_wall = time.monotonic() - t_start
        print(f"\nDone: {len(sections)} sections rendered to {out_dir}/ ({total_wall:.1f}s total)")
        return

    # ── Legacy: render all, export only the last one ─────────────
    for i, sc in enumerate(sections):
        template = sc["template"]
        header = sc.get("header") or sc.get("title", "")
        print(f"Rendering section {i}: {template} — {header}")
        clip = _render_section(sc, video_settings, colors, preview_duration)
        print(f"  Duration: {clip.duration:.1f}s")
        final = clip

    print(f"\nResolution: {resolution[0]}x{resolution[1]}, {fps}fps")
    print(f"Writing to: {output_path}")
    _export_clip(final, output_path, fps)
    print(f"\nDone: {output_path}")


# ── CLI entry point ───────────────────────────────────────────────


def main(args=None):
    parser = argparse.ArgumentParser(
        description="V3 compositor — render YAML manifest to mp4.",
    )
    parser.add_argument(
        "--manifest", required=True,
        help="Path to YAML manifest file",
    )
    parser.add_argument(
        "--output",
        help="Output mp4 path, or directory for --render-all",
    )
    parser.add_argument(
        "--section", type=int, default=None,
        help="Render only this section index (0-based)",
    )
    parser.add_argument(
        "--render-all", action="store_true",
        help="Render every section to --output directory (one mp4 each)",
    )
    parser.add_argument(
        "--workers", type=int, default=1,
        help="Number of parallel workers for --render-all (default: 1)",
    )
    parser.add_argument(
        "--preview-duration", type=float, default=None,
        help="Cap each section to N seconds for fast layout iteration",
    )
    parser.add_argument(
        "--validate", action="store_true",
        help="Validate manifest only — check paths, don't render",
    )
    args = parser.parse_args(args)

    if args.validate:
        config = load_manifest(args.manifest)
        validate_paths(config)
        print(f"Manifest valid: {len(config['sections'])} sections")
        for i, s in enumerate(config["sections"]):
            t = s["template"]
            lbl = s.get("label", "")
            h = (s.get("header") or s.get("title", "")).replace("\n", " ")[:60]
            tag = f" [{lbl}]" if lbl else ""
            print(f"  {i}: {t}{tag} — {h}")
        print("All paths verified.")
        return

    if not args.output:
        parser.error("--output is required (unless using --validate)")

    if args.section is not None and args.render_all:
        parser.error("--section and --render-all are mutually exclusive")

    compose(
        args.manifest, args.output,
        section_index=args.section,
        render_all=args.render_all,
        preview_duration=args.preview_duration,
        workers=args.workers,
    )


if __name__ == "__main__":
    main()
