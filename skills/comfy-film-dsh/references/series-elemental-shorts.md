# Elemental Creatures — series profile

> **This is the author's series profile, not part of the generic kit.** It is kept as a worked
> example of how one series pins its format, pacing and look. Delete it, or copy it to your own
> `references/<series>.md` and rewrite the facts, before running the skill for somebody else's series.
> Read it at the start of a session that touches this series; the controller itself is described in
> `SKILL.md` and the other references.

A YouTube Shorts series of tiny creatures built from natural material: water, glass, amber, coral, leaves, moss, petals, stones. One creature per film. The hook is always the same: ordinary material becomes a creature, the creature does something characterful, then the film closes on the state it started from.

## Format

- Canvas 608×1056 portrait, 24 fps, Turbo 8 (8 steps), H3 FL2VA. For more real detail start a new project at 768×1344 (H3 native portrait) — the whole chain must share one canvas.
- Delivery: `finalize_delivery.py` runs finalize and a single SeedVR2 3B FP16 ×2 pass, delivering `<name>-final-vN.mp4` and `<name>-final-vN-2x.mp4`. Native FPS and soundtrack are preserved; H.264 yuv420p/AAC, frame count, dimensions and decode are verified. Review invented details and temporal stability. `--no-upscale` only for explicit exceptions.
- 3 segments × 10 s ≈ 30 s, or 2 segments when the story is shorter. Speed-up to 1.3× on request is common and accepted.
- Static camera, fixed lens/focus/exposure for the entire film. No cuts inside a segment.
- Scene audio only: stream, wind, wet clicks, small knocks. `non_diegetic_music: N/A`.
- Loop when the story allows it: final frame returns to the exact opening frame.

## Look

Photoreal fantasy macro miniature. Golden backlit forest or pond, shallow depth of field, soft bokeh, wet surfaces, tactile material detail, oversized expressive eyes. The creature should read instantly as an animal and as the material it is made of.

Delivery channel and playlist: whatever `assets/youtube.json` configures (this series used a dedicated playlist), category 22, English, `containsSyntheticMedia: true`, `madeForKids: false`, notify subscribers on.

## Story shapes that worked

- Material assembles into the creature, the creature performs one gag, material returns. (River pebble frog, glass dragonfly, amber bee, coral crab, gem fly)
- Existing frames from the user, glued by one short action. (Crumb ant, roach courier series)
- Creature emerges from its own home, reacts to an outside event, retreats. (Moss snail)

## Prompt defaults per part

- Part 1: assemble / emerge. First frame = material or empty scene, last frame = design pose (FL2VA). State the material inventory once, then the assembly order in timed beats.
- **Part 2 onward: always `--guide prev --guide-frames 22 --last <board>`, 5–6 s.** Never restart a take from a board — the boards are separate generations and their few-percent drift reads as a hop in scale and position at the cut, whatever the whole-frame difference says. The guide carries the previous clip's real motion in; `--last` lands the beat on its board.
- Final part: `--loop` cannot be combined with `--guide`. Extract `frames/segment-0001-first-1x.png` (`film extract --segment 1 --which first --scale 1`) and pass it as `--last`, so the loop closes on the exact opening frame.

## Checks per part

- **Two passes: the whole film at 384×672 first, then native.** `film preview --project PROJECT` makes a 384×672 sibling with 5 s takes (~30 s each instead of ~10 min); the entire film — every segment, trims, joins, loop close — is built and approved there as one cut, and only then is the same segmentation shot again at 768×1344 from the same boards and prompt files. A guide chain never crosses the passes, and the previz project stays on disk as the reference cut. Paper flattening is the cautionary case: six native takes before a 61 s previz take proved it was the model, not the prompt.
- The prep in part 2 must change the silhouette, not just move: a contact sheet every 0.5 s has to show distinct poses from the first second. "Rocks and trembles" alone reads as standing.
- Check every join against the frame that is actually shown: the last frame of part N against **frame 22** of part N+1 (the guide frames are trimmed). A number under 4 can still hide a shifted subject — look at both stills.
- Every FL2VA tail ends still; trim 0.75–1.25 s (multiples of 1/24 s) so part N+1 cuts in while the creature is still moving.
- If the last frame of a part is the apex of a jump or the settled design pose, expect a hang — cut it in post rather than re-rendering.
- Run `motion_profile.py` on the assembled film before asking for final approval: any dead run longer than 0.5 s outside the opening and the closing pile needs a reason.

## Bookkeeping

One project per creature: `$Series/<english name>`. `brief.md` records creative intent, technical settings, approvals with file names, assembly notes and the published URL. `youtube.json` holds the approved metadata and the publication record.
