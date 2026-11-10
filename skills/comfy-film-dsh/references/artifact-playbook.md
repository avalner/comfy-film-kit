# Artifact playbook

Every entry is a failure observed in production, its real cause, and the cheapest reliable fix. Try the deterministic fix before spending another render.

## Vegetation grows, swells, deflates

Symptom: moss or leaves inflate and settle during a shot where nothing should change.

Causes, in order of importance:
1. The two keyframes show the same background in different states. FL2VA interpolates between them, and the most textured region (moss) morphs first.
2. The prompt lists the forbidden behaviours ("no swelling, no sprouting, no spikes"). H3 is not a negative-prompt model; those words still steer.
3. The story action invites a plant reaction ("something emerges from the moss").

Fixes:
- Derive the last keyframe from the first by image editing (add the creature, keep everything else), so only the creature differs.
- Replace the negative list with one positive sentence: "the moss holds one and the same matte surface for the whole shot".
- Change the mechanism so the plant is not involved: the creature walks in from the edge instead of emerging from the moss.

## The creature drifts (wrong colour, wrong eyes, melting eyes)

Symptom: a pale, orange-eyed creature instead of the approved design; eyes collapsing into smooth green bulbs.

Causes: an I2VA shot with no last frame lets the model invent the creature. Even with a last frame, H3 treats it as a target, not a lock, so mid-shot drift is possible.

Fixes:
- Always pass the design still as the last frame, or start the film from the design frame.
- Keep eyes described as eyes in every beat: "both eyes keep their round shape"; if the story requires them to retract, say "the stalks pull in one after the other" and keep the shape language for the re-extension.
- Reject and re-run with another seed if the drift happens mid-shot despite this.

## Unsolicited water beads on a surface

Symptom: large glassy droplets appear on the shell, leaf or stone and stay there.

Cause: prompts mentioning "water beads rolling off" or wet surfaces; the model keeps the beads instead of removing them.

Fix: state the dry positive once ("the shell stays dry and matte, its surface unchanged"), and avoid mentioning droplets at all. If the beads still appear, reject the take; if the rest of the take is too good to lose, mask them out with ProPainter (`references/post-tools.md`).

## Debris and particles at an impact

Symptom: moss, crumbs or dust spray out when something lands.

Cause: the prompt asked for the impact too vividly ("loose moss and crumbs puff out").

Fix: describe the impact without debris ("the shell settles slowly with no jolt"), or accept a soft settle instead of a hit.

## Pause before a reaction

Symptom: an acorn lands, then the creature reacts a second later.

Cause: the model stretches the reaction; the beat structure in the prompt does not survive.

Fix (deterministic): find the impact frame and the first reaction frame, cut the gap, join with a 0.10–0.15 s crossfade. Do not regenerate for timing alone. Verify the reaction is now within ~0.15 s of the impact.

## Visible joint between segments

Symptom: a jump at a cut even though pose and framing match.

Cause: the generated segments shift overall light and background sparkle.

Fix: 4-frame crossfade (0.167 s) per boundary, audio `acrossfade` at the same length. Optical joins (DIS flow) ghost the subject — use them only for genuinely matching motion, and inspect frames on both sides.

## The final frame refuses to match the loop target

Symptom: to reach the opening still the model deletes a story object (the acorn vanishes), or the object stays and the loop breaks.

Fix: make the story remove the object itself (the creature shakes it off and it rolls out of frame), or end deterministically by dissolving the last ~0.6–1.4 s into the opening still. A short dissolve reads as an intentional close; a long one ghosts.

## Fast eye movement smears

Symptom: during a rapid shake the eyes blur into a green blob for a few frames.

Cause: 24 fps plus fast lateral motion.

Fix: do not write rapid eye vibration. If it exists in an accepted take, either cut the 0.3–1 s window with a crossfade, or slow that passage down rather than regenerating.

## The preparation looks like standing still

Symptom: a "long wind-up" renders as the creature posing at the camera for five seconds, then
jumping. The user sees a frozen character, not anticipation.

Cause: the beats describe incremental motion — "rocks back and forth in small increments",
"trembles", "coils tighter". H3 renders the motion, so the motion metric looks healthy, but the
silhouette never changes and the audience reads a still pose. This is not caught by
`motion_profile.py`; only a contact sheet catches it.

Fix: write poses that change the outline, three or four of them, each held only briefly:
turn to face the target → stretch one hind leg out behind, then the other → drop the belly to the
stone with the front legs braced and the head low between them → ratchet the folded legs tighter
and rock → launch in the last ~2 s. Check a 0.5 s contact sheet before showing the take; reject and
rewrite rather than re-rolling the same prompt.

## Every FL2VA clip ends frozen

Symptom: the last second of a clip is motionless, and the cut to the next part lands on a held
pose. Two of these in a row read as the video pausing.

Cause: structural. FL2VA interpolates into its last frame, so it decelerates into it. `keyframe`
locking works on the pose, never on the pacing.

Fix: measure (`motion_profile.py`), then trim the tail — 0.75–1.25 s is typical. Cut on a multiple
of 1/24 s. For an assembly, the still design pose is the right last frame, so trim the still and
let the next part start moving immediately. Do not re-render for a tail ease.

## Hanging at the top of a jump

Symptom: the creature leaps and then hovers at the apex for a second or more.

Cause: the last frame is the apex. The model reaches it early and holds.

Fix (post): trim the take at the moment the feet leave the stone and start the next part after the
apex, so the cut itself supplies the middle of the arc — rise → cut → fall. Match the two frames
first (`keyframe_check.py`; ~6 means the cut is invisible). If the hop must be continuous, do not
put the apex on the last frame: let the clip end on the landing and use the airborne still as a
reference only.

## Long static holds

Symptom: the creature stands motionless for a second or more, usually right before a cut.

Fix: trim the idle tail and start the next segment on movement; keep deliberate pauses only where the story needs them.
