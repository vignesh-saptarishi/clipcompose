"""Assembly pipeline -- temporal composition of rendered sections.

Takes a list of section dicts (each with a moviepy clip, transition duration,
and transition type) and assembles them into a single timeline.

Transition types:
  - crossfade: clips overlap by `transition` seconds with cross-dissolve.
  - fade_to_black: outgoing clip fades out, incoming clip fades in.
    Each fade takes transition/2 seconds. No overlap.

A transition duration of 0 is always a hard cut, regardless of type.

The transition field on each section controls the *outgoing* transition
(how this section transitions INTO the next one). The last section's
transition is ignored (nothing follows it).
"""

from moviepy import CompositeVideoClip, vfx


def assemble_sections(
    sections: list[dict],
    fps: int = 30,
) -> CompositeVideoClip:
    """Assemble section clips into a single timeline.

    Each section dict must have:
      - clip: a moviepy VideoClip
      - transition: float >= 0 (outgoing transition duration in seconds)
      - transition_type: "crossfade" or "fade_to_black"

    The algorithm walks through sections left-to-right, maintaining a
    running "current_t" cursor. For each clip it:
      1. Applies incoming effects (based on the PREVIOUS section's
         outgoing transition type and duration).
      2. Applies outgoing effects (based on THIS section's transition
         fields, but only if this isn't the last section).
      3. Sets the clip's start time on the timeline.
      4. Advances current_t -- subtracting the overlap for crossfades,
         or stepping forward by the full clip duration for cuts and
         fade-to-black (which have no temporal overlap).

    Args:
        sections: List of section dicts with clip, transition, transition_type.
        fps: Output frame rate.

    Returns:
        CompositeVideoClip with all sections on a shared timeline.

    Raises:
        ValueError: If sections list is empty.
    """
    if not sections:
        raise ValueError("No sections to assemble")

    # Single section: nothing to compose, just set fps and return.
    if len(sections) == 1:
        return sections[0]["clip"].with_fps(fps)

    # Build timeline: compute start time and apply effects for each clip.
    timeline = []
    current_t = 0.0

    for i, sec in enumerate(sections):
        clip = sec["clip"]
        out_transition = sec["transition"]
        out_type = sec["transition_type"]

        effects = []

        # --- Incoming effects ---
        # Based on the PREVIOUS section's outgoing transition. The previous
        # section decides how it hands off to us: crossfade means we fade in
        # during the overlap period; fade_to_black means we fade in from
        # black over half the transition duration.
        if i > 0:
            prev = sections[i - 1]
            in_t = prev["transition"]
            in_type = prev["transition_type"]
            if in_t > 0:
                if in_type == "crossfade":
                    effects.append(vfx.CrossFadeIn(in_t))
                elif in_type == "fade_to_black":
                    effects.append(vfx.FadeIn(in_t / 2))

        # --- Outgoing effects ---
        # Based on THIS section's transition fields. Only applied if
        # there's a next section (last section's transition is ignored).
        # crossfade: cross-dissolve out over the full transition duration.
        # fade_to_black: fade to black over half the transition duration.
        if i < len(sections) - 1 and out_transition > 0:
            if out_type == "crossfade":
                effects.append(vfx.CrossFadeOut(out_transition))
            elif out_type == "fade_to_black":
                effects.append(vfx.FadeOut(out_transition / 2))

        # Apply all accumulated effects to the clip.
        if effects:
            clip = clip.with_effects(effects)

        # Place clip at current timeline position.
        clip = clip.with_start(current_t)
        timeline.append(clip)

        # --- Advance the timeline cursor ---
        # Crossfade: clips overlap by the transition duration, so the next
        # clip starts before this one ends.
        # Cut / fade_to_black: no overlap, next clip starts right after.
        if i < len(sections) - 1:
            if out_transition > 0 and out_type == "crossfade":
                current_t += clip.duration - out_transition
            else:
                current_t += clip.duration

    # Total duration = furthest end point of any clip on the timeline.
    total_duration = max(c.start + c.duration for c in timeline)
    result = CompositeVideoClip(timeline).with_duration(total_duration).with_fps(fps)
    return result
