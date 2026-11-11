# Tested painting workflow

Read when planning a new painting video. This recipe comes from Living Cafe Painting (2026-11-06); use its principles, not its scene-specific coordinates or approval records.

## What was learned

| Observed failure | Working response |
|---|---|
| Generating the approach changed perspective inside a supposedly flat painting. | Deterministic planar enlargement; generate only the living scene. |
| Enlarging the small painting baked into the room reference was blurry. | Composite the original full-resolution artwork separately, then sample the composed image for each output frame. |
| Generated room images subtly redrew the original artwork. | Treat the generated room as the room/frame source; use the original artwork as the insert rather than relying on the redrawn detail. |
| The animation invented a hand opening a door/window in front of the scene. | Start a new still-anchored action at the tight artwork endpoint and describe only the visible scene and intended small motions. |
| A long negative description mentioning hands, windows and doors still produced those objects. | A short affirmative prompt succeeded on the next attempt. This is evidence from one project, not a guarantee of model behavior; inspect the full result. |
| A separately generated full-screen artwork had a different composition from the approached painting. | Use the actual accepted approach endpoint as the animation anchor. |
| Upscaling started although the user did not need it. | Native final by default, explicit `--no-upscale`; upscale only when requested. |
| Inline video did not appear to the user. | Include a direct Markdown link to the MP4 in every review. |
| The cut from the crisp composited approach to the first H3 frames read as a brightness jump. | Measure per-frame luma on the assembled cut; when the join is the largest step, dissolve the take's opening 12 frames from the approach's real last frame. |
| A patched rebuild came out one frame late and shifted the whole cut. | The rawvideo pipe of an assembled film repeats its first frame (the file starts at ~0.021 s); drop it before patching, and locate the cut by matching the endpoint image instead of a hard-coded index. |

## Geometry and source detail

Measure the inner artwork rectangle or quadrilateral in the room reference, not the outer frame. Fit the high-resolution original without stretching. Prefer a front-facing frame; if needed, use a fixed homography for perspective and keep it constant during the approach. Choose the crop deliberately and preserve it through the animation join.

For each zoom frame, sample the high-resolution composition. With final zoom Z, the tightest crop in composition pixels is canvas width/Z by canvas height/Z. Check the actual source-artwork density within that crop against output resolution; enlarging a low-resolution source canvas cannot recover details. Retain the painting insert at sufficient resolution before any output downsampling. Smooth easing at the beginning/end prevents abrupt camera starts.

For the retreat, map the accepted animation's selected endpoint back onto the same canvas crop that produced its starting image. The living image can differ at the edges after generation: inspect the composite at close, middle and distant scales. Do not hide an obvious registration problem with a long dissolve or regenerate accepted material without authorization.

## Successful H3 prompt shape

Use the actual scene and chosen duration; this ten-second example is a starting point, not a mandatory story. The first image is the accepted tight artwork endpoint, with the room and frame outside the image.

```text
For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.

integrated_multimodal_description: [Shot 1] A ten-second locked-off tripod shot of this exact nighttime cafe street. The view remains precisely matched to Picture 1 throughout: the same yellow cafe awning at left, seated diners, waiter in a white apron, marble tables, wicker chairs, wet cobblestones, couple on the right, distant tower and blue starry sky. The waiter gently leans toward an existing table and serves a drink. Diners make tiny natural head movements. The existing couple takes two slow steps farther down the street. Candle flames flicker softly and the lower edge of the yellow awning stirs gently in the breeze. Warm reflected highlights shimmer subtly on the wet cobblestones. All buildings and furniture retain their exact positions and proportions. The camera stays fixed at the same street viewpoint, with the entire image filled by the cafe street throughout. Preserve the crisp detailed realistic appearance and warm amber and deep blue lighting of Picture 1.

overall_soundscape: Soft outdoor cafe ambience, faint ceramic clinks, light footsteps on wet stones and a gentle breeze.

non_diegetic_music: N/A
```

Generation is still reviewed. Do not promise that the prompt guarantees fixed geometry or absence of artifacts.

## Joining the living take onto the still approach

The approach ends on the composited artwork; H3 opens on its own redraw. Geometry normally matches (measured 0 px shift, scale 1.000 in Living Tulip Balloons), but the take's first frames are flatter and a little darker and the sky is redrawn, so the cut is visible as a brightness change.

Diagnose on the assembled film, not by eye: decode it once and print per-frame mean luma; the join must not produce the film's largest single-frame step (Living Tulip Balloons: -2.04 at the cut against 0.85 after the fix and 1.4 later in the sunset).

Repair without retiming:

1. Decode the cut to yuv420p frames; drop the first frame the rawvideo pipe repeats, and find the cut frame by matching `references/approach-end.png` (a hard-coded index is off by one whenever the pipe duplicates).
2. For the 12 frames after it, write `(1 - k/12) * approach_endpoint + (k/12) * take_frame` in YUV, all three planes.
3. Re-encode the whole film once at CRF 15 and re-mux the existing audio unchanged, or patch only the join if the controller's clips are still available.

The dissolve starts exactly on the picture the camera stopped on, so the first frame of the take cannot jump, and the redrawn sky arrives as the painting waking up. Keep it 0.5 s: longer blends ghost the drifting subject.

## Controller and delivery

Use comfy-film commands for the project. For this still-to-life transition, `add --first ACTUAL_ENDPOINT --seconds SECONDS --prompt-file PROMPT` starts the intended new action. For an existing rejected candidate, the shared controller also supports `run --segment N --first ACTUAL_ENDPOINT --seconds SECONDS --prompt-file PROMPT` to remove its previous motion guide and revise the input; only use after the relevant rejection/retry authorization.

Deterministic montage clips can be imported for review. `import --replace-rejected --file VIDEO` replaces only the latest rejected candidate, retaining previous candidate history; it cannot replace accepted media. Only call `accept` after the user explicitly accepts the exact clip.

When a run's response or state write fails after possible submission, use `status` and `recover`, not a duplicate run. A transient film.json access error in this project was recovered successfully.

Final processing remains through the existing wrapper:

```powershell
python '$Tools/skills/comfy-film-dsh/scripts/finalize_delivery.py' --project PROJECT --name NAME --deliver-dir OUTPUTS --no-upscale
```

Keep project-specific reproduction details and source paths in that project's `brief.md`. The example's timing was 5+10+5 seconds at 24 fps, 768x1344, Turbo 8; the accepted living clip generated 243 frames and used a 3-frame tail trim for exactly 10 seconds. Music was subsequently mixed as a new final version; scene ambience was reduced to 25% amplitude, with 0.5s music fade-in and 1.5s fade-out. Reconsider these values for each new scene and supplied track.
