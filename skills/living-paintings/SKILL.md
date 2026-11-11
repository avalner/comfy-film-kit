---
name: living-paintings
description: Create videos in which a camera approaches a framed painting in a room, the depicted scene comes alive, and optionally the camera pulls back. Use for оживающие картины and subsequent videos in the Paintings series; not for generic films or standalone image edits.
---

# Living paintings

Use this skill for the visual design and compositing of painting videos. Use the installed `comfy-film` controller for generation, reviews, recovery and final delivery: in Codex `~/.codex/skills/comfy-film/SKILL.md`, in DeepSeek Harness the `comfy-film-dsh` skill (`~/.dsh/skills/comfy-film-dsh/SKILL.md`). Both drive the same `$Tools/comfy-film/scripts/film.py`; only the surrounding tools differ. Read the relevant references as needed; do not recreate its controllers. For substantive H3 prompts use `h3-prompt-writing`.

## Harness differences (DeepSeek Harness)

| Codex habit | DSH replacement |
|---|---|
| Codex browser panel for the progress page | Start `progress.py --serve` as a background job and post the verified URL from `.pipeline/progress-server.json` |
| Menu tool for accept/change/reject | `ask_user_question` with two-word labels; links and numbers belong in the message above it |
| Images trusted to render in chat | Path link in angle brackets for images/documents; `http://127.0.0.1:8199/watch/...` for every clip (server: `comfy-film-dsh/scripts/serve-media.py`) |
| Drafting delegated to a sub-agent | Draft in the parent; DSH has no drafting delegation for these films |
| Final processing | `comfy-film-dsh/scripts/finalize_delivery.py --input ... --no-upscale` |

Publication, reviews and montage rules are unchanged; they live in the comfy-film skill.

## Start or resume

- Keep projects under `$Paintings/<English name>`. Store original artwork, room reference, prompts, generated takes, montage clips and final exports inside that project. Avoid dependencies on clipboard/temp files or another project's output folder.
- On resume, run `film status --project PROJECT` and read the current `brief.md`. Technical state lives in `film.json`; approvals are not inferred from file existence.
- For a new painting, read [workflow.md](references/workflow.md) before designing keyframes or generating video. It contains the tested recipe and specific failures from Living Cafe Painting.
- Reuse the user's supplied format, timing, sound and camera choices. The previous film's 5s approach + 10s animation + 5s retreat is an example, not an automatic choice for every painting.

## Separate room motion from artwork animation

1. Design a room reference with the framed painting front-facing and sufficient room around it for the intended approach. Keep the original high-resolution artwork as a separate source.
2. When the user wants the artwork static during approach, composite that original artwork into the frame and animate a uniform planar crop/scale deterministically. Do not ask H3 to invent the room-to-street move: in the tested project it changed internal perspective. Do not zoom the tiny baked-in painting in the room image: it becomes blurry.
3. Render the approach so that its final frame is fully inside the artwork. Check that the original artwork has enough pixels for the tightest crop. A high-resolution room canvas helps compositing precision, but does not add artwork detail; preserve the original source's pixels until the final output sampling.
4. Start the living scene from the actual accepted approach endpoint. This is deliberately a new action from a still pose: use I2VA with that still, rather than carrying the room/approach as a moving guide. The guide default in comfy-film remains appropriate for continuing an already living action, not this transition.
5. Use a short affirmative prompt describing the fixed street/landscape viewpoint and a few small movements within the depicted scene. Do not describe entering or passing through the painting. See the successful prompt pattern in workflow.md.
6. For a static-artwork retreat, freeze the actual selected last frame of the accepted living scene, register it in the high-resolution room/artwork composition and animate the inverse planar crop/scale. Do not reset to the original artwork's earlier character poses at the join. Inspect edges for registration seams; use restrained feathering only where suitable.

Keep camera motion and depicted motion independently controllable. Generative camera moves may be used when the user wants perspective changes; the flat-artwork method applies to the static-artwork concept.

### The join onto the living take is where the eye catches a jump

H3 does not copy its conditioning still: it re-renders its first frames, which come out flatter and a couple of luma darker, with a redrawn sky. Against the crisp composited approach frame this reads as a brightness step at the cut even though scale and offset match exactly. In Living Tulip Balloons the cut carried the film's largest single-frame luma step (-2.04) while the join measured 0 shift and 1.000 scale.

Measure it, do not guess: decode the assembled cut once and print the per-frame mean luma; the join must not be the largest step in the film. When it is, replace the take's opening 12 frames with a deterministic dissolve that starts on the approach's actual last frame and converges onto the take's own frames (weight k/12). Nothing is retimed, nothing is invented, and the first shown frame of the take is exactly the picture the camera stopped on. Recipe and numbers: [workflow.md](references/workflow.md).

## Reviews and finishing

- Follow comfy-film's frame, clip and final review gates. Deterministic fitting of approved sources and endpoint extraction inherit their source approval; a new generative room or artwork redraw needs its own review.
- Before showing an animation candidate, inspect its full timeline for foreground hands, opening panels/windows, unwanted camera motion, layout drift, character artifacts and loss of detail. Successful decoding alone is not visual approval. On failure, disclose it and follow comfy-film's authorized retry rules.
- Use the actual trimmed endpoints for joins. H3 rounds duration; remove only the required excess frames to meet the selected plan. Preserve accepted source clips and versions.
- With supplied music, keep video unchanged when possible; save a new final version. Set the music/ambience balance and fades for the supplied track rather than blindly reusing the first film's mix.
- Final upscale is optional: use `finalize_delivery.py --no-upscale` unless explicitly requested. Produce H.264 yuv420p/AAC with faststart and verify decoding. Give a clickable local MP4 link; an inline video alone was not visible to the user in the tested chat.
- Save the selected geometry, source versions, prompts, accepted takes, trims, mix and final review status in `brief.md`. Record a new reusable lesson here only when it changes future decisions; keep one-off coordinates in the project.

## Existing example

`$Paintings/Living Cafe Painting` is the tested example. Its `brief.md` preserves decisions and rejected variants; `clips/` contains accepted segments; `.pipeline/drafts/prompts/part2-v4.txt` is the successful living-scene prompt. Final v2 includes the user's music and still awaits explicit final-film approval. These facts do not approve future films or authorize publication.
