"""CLI for assembly — merge pre-rendered sections into a final video.

Uses native ffmpeg instead of moviepy, so ffmpeg handles all frame I/O
internally — no Python frame loop bottleneck.

Transition behavior matches the moviepy-based assembler:
  - crossfade: clips overlap by T seconds (xfade filter).
  - fade_to_black: NO overlap. Outgoing clip fades out over T/2,
    incoming clip fades in over T/2. Clips placed sequentially
    via concat (fade filters applied per-clip).
  - hard cut (T=0): sequential concat, no effects.

Two-step workflow:
  1. Render individual sections with clipcompose.cli (spatial layout).
  2. Merge them in time with this CLI (temporal composition).

Usage:
    python -m clipcompose.assemble_cli \
        --manifest assembly-manifest.yaml \
        --output final.mp4
"""

import argparse
import subprocess
from pathlib import Path

import imageio_ffmpeg
from moviepy import VideoFileClip

from .assembly_manifest import load_assembly_manifest, validate_assembly_paths


_FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()


def _get_duration(path):
    """Get video duration in seconds using moviepy."""
    with VideoFileClip(path) as clip:
        return clip.duration


def _build_filter_graph(sections):
    """Build an ffmpeg filter graph that matches moviepy assembly behavior.

    The key distinction: crossfades overlap clips temporally (xfade filter),
    but fade_to_black does NOT overlap — each clip plays its full duration
    with fade effects applied at the edges, then concat joins them.

    Algorithm:
      1. Group consecutive clips connected by crossfades.
      2. Within each group, chain clips with xfade=fade (overlapping).
      3. Apply fade=in / fade=out at group boundaries for fade_to_black.
      4. Concat all groups sequentially (no overlap between groups).

    Returns (filter_graph_string, expected_duration, output_label).
    """
    n = len(sections)

    # ── Step 1: group clips by crossfade chains ──────────────────
    # A new group starts whenever the outgoing transition is NOT crossfade.
    groups = []
    current_group = [0]
    for i in range(n - 1):
        t = sections[i]["transition"]
        tt = sections[i]["transition_type"]
        if t > 0 and tt == "crossfade":
            current_group.append(i + 1)
        else:
            groups.append(current_group)
            current_group = [i + 1]
    groups.append(current_group)

    filter_parts = []
    group_results = []  # (label, duration) per group

    for gi, group in enumerate(groups):

        # ── Step 2: xfade within group (crossfade chains) ────────
        if len(group) == 1:
            base_label = f"[{group[0]}:v]"
            base_dur = sections[group[0]]["duration"]
        else:
            running = sections[group[0]]["duration"]
            for j in range(len(group) - 1):
                src_idx = group[j]
                dst_idx = group[j + 1]
                xd = sections[src_idx]["transition"]
                offset = max(0.0, running - xd)

                in1 = f"[{group[0]}:v]" if j == 0 else f"[xf{gi}_{j}]"
                in2 = f"[{dst_idx}:v]"
                out = f"[xf{gi}_{j + 1}]"

                filter_parts.append(
                    f"{in1}{in2}xfade=transition=fade"
                    f":duration={xd:.3f}:offset={offset:.3f}{out}"
                )
                running += sections[dst_idx]["duration"] - xd

            base_label = f"[xf{gi}_{len(group) - 1}]"
            base_dur = running

        # ── Step 3: fade effects at group boundaries ─────────────
        # Incoming: if previous group ended with fade_to_black, fade in.
        # Outgoing: if this group ends with fade_to_black, fade out.
        fades = []

        if gi > 0:
            prev_last_idx = groups[gi - 1][-1]
            pt = sections[prev_last_idx]["transition"]
            ptt = sections[prev_last_idx]["transition_type"]
            if pt > 0 and ptt == "fade_to_black":
                fades.append(f"fade=t=in:st=0:d={pt / 2:.3f}")

        last_in_group = group[-1]
        if last_in_group < n - 1:
            ot = sections[last_in_group]["transition"]
            ott = sections[last_in_group]["transition_type"]
            if ot > 0 and ott == "fade_to_black":
                fade_start = base_dur - ot / 2
                fades.append(f"fade=t=out:st={fade_start:.3f}:d={ot / 2:.3f}")

        if fades:
            out_label = f"[grp{gi}]"
            filter_parts.append(f"{base_label}{','.join(fades)}{out_label}")
        else:
            out_label = base_label

        group_results.append((out_label, base_dur))

    # ── Step 4: concat all groups ────────────────────────────────
    total_dur = sum(d for _, d in group_results)

    if len(group_results) == 1:
        label = group_results[0][0]
        # If the label is a raw input like [0:v], we can map it directly.
        # Otherwise it's already a filter output label.
        return ";".join(filter_parts), total_dur, label

    concat_in = "".join(lbl for lbl, _ in group_results)
    filter_parts.append(
        f"{concat_in}concat=n={len(group_results)}:v=1:a=0[vout]"
    )
    return ";".join(filter_parts), total_dur, "[vout]"


def assemble(
    manifest_path: str,
    output_path: str,
) -> None:
    """Load assembly manifest, validate paths, assemble via native ffmpeg.

    Builds an ffmpeg filter graph and runs ffmpeg as a subprocess.
    No moviepy frame loop — ffmpeg handles all demuxing, filtering,
    and encoding internally.

    Args:
        manifest_path: Path to YAML assembly manifest.
        output_path: Output mp4 path.
    """
    config = load_assembly_manifest(manifest_path)
    validate_assembly_paths(config)

    video = config["video"]
    fps = video["fps"]

    sections = config["sections"]
    if not sections:
        print("No sections to assemble.")
        return

    # Probe durations.
    print(f"Probing {len(sections)} sections...")
    for i, sec in enumerate(sections):
        sec["duration"] = _get_duration(sec["path"])
        print(f"  [{i}] {sec['duration']:.1f}s  {sec['path']}")

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    _codec_params = ["-crf", "20", "-pix_fmt", "yuv420p"]

    n = len(sections)

    # Single section: just re-encode.
    if n == 1:
        cmd = [
            _FFMPEG, "-y", "-i", sections[0]["path"],
            "-c:v", "libx264", *_codec_params,
            "-r", str(fps), "-an", output_path,
        ]
        print(f"Single section — re-encoding to {output_path}")
        subprocess.run(cmd, check=True)
        print(f"\nDone: {output_path}")
        return

    # Build filter graph.
    filter_graph, expected_dur, out_label = _build_filter_graph(sections)

    # Assemble ffmpeg command: N inputs + filter_complex + output.
    inputs = []
    for sec in sections:
        inputs.extend(["-i", sec["path"]])

    cmd = [
        _FFMPEG, "-y",
        *inputs,
        "-filter_complex", filter_graph,
        "-map", out_label,
        "-c:v", "libx264", *_codec_params,
        "-r", str(fps),
        "-an",
        output_path,
    ]

    print(f"\nAssembling {n} sections (native ffmpeg)...")
    print(f"Expected duration: ~{expected_dur:.1f}s")
    print(f"Writing to: {output_path}")
    subprocess.run(cmd, check=True)
    print(f"\nDone: {output_path}")


def main(args=None):
    parser = argparse.ArgumentParser(
        description="Assembly CLI — merge pre-rendered sections into a final video.",
    )
    parser.add_argument(
        "--manifest", required=True,
        help="Path to YAML assembly manifest",
    )
    parser.add_argument(
        "--output",
        help="Output mp4 path (required unless --validate)",
    )
    parser.add_argument(
        "--validate", action="store_true",
        help="Validate manifest only — check paths, don't render",
    )
    args = parser.parse_args(args)

    if args.validate:
        config = load_assembly_manifest(args.manifest)
        validate_assembly_paths(config)
        print(f"Assembly manifest valid: {len(config['sections'])} sections")
        for i, s in enumerate(config["sections"]):
            t = s["transition"]
            tt = s["transition_type"]
            print(f"  {i}: {s['path']} -> {tt} ({t}s)")
        print("All paths verified.")
        return

    if not args.output:
        parser.error("--output is required (unless using --validate)")

    assemble(args.manifest, args.output)


if __name__ == "__main__":
    main()
