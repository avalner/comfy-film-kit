# Assembly

Stitch only explicitly accepted clips. Explicit approval of a named batch authorizes accepting those named clips. Importing does not itself imply acceptance.

Default joins are cuts: appropriate for scene changes and matching continuations. Never apply global stabilization to a film with intentional camera motion. Set measured pauses with per-clip trim. For a small continuation mismatch use a per-boundary optical or crossfade join, usually 0.25 seconds. Optical flow can distort faces, smoke, occlusions or large motion; it is an option, not a quality guarantee. Do not morph every scene change.

`stitch` preserves originals, normalizes resolution/fps/audio, writes a new export and decodes it to check errors. Name the final deliverable exactly `<video name>-final-<version>.mp4`, e.g. `autumn-leaf-fawn-final-v1.mp4`, without extra suffixes. Increment the version for a revised final and preserve earlier versions. Descriptive intermediate filenames are allowed; the delivered playback file must follow this pattern.

Final playback MP4s use H.264 (`-pix_fmt yuv420p -profile:v high -tag:v avc1`), AAC audio when present, and `-movflags +faststart`. Apply the same output settings after all finishing steps; RGB raw input otherwise lets libx264 choose unsupported High 4:4:4. Verify `codec_name=h264` and `pix_fmt=yuv420p` with ffprobe after the last encode, alongside the decode check. Show the final film. If a seam is bad, inspect and change only that boundary; do not rework the whole film or regenerate accepted clips without authorization.

Processing is streamed per clip with bounded transition windows, not an in-memory array of the whole film. No fixed film-length or segment-count limit is imposed; disk, hardware and codecs remain practical constraints.

Persisted state: film.json, clips/, frames/, and .pipeline/ for input copies, reviews, workflow snapshots and export intermediates. Preserve these for other chats. Do not auto-delete caches.


## Automatic continuity finishing

Before showing a first assembly of a continuous creature scene, inspect short windows around each join for pose/motion continuity, unnecessary holds, whole-frame lighting/contrast jumps and sound discontinuities. Perform justified local finishing within the authorized edit without asking the user to diagnose routine assembly issues. This is an agent workflow, not an automatic feature of `stitch`. Record trims, joins, corrections and the source segment mapping in the project.

- Start from actual accepted endpoint frames. Remove duplicate boundary frames and measured idle tails when they delay an intended continuous action; preserve deliberate pauses and requested gestures. Do not alter an approved action merely to shorten it.
- Keep matching cuts when they work. For small mismatches, try a short optical join (roughly 4–6 frames at 24 fps), inspect the result, and adjust only that boundary. Crossfades on moving faces/limbs can create double images; optical flow can warp water, faces and tails. Neither is a universal default.
- For a static camera with consistent intended lighting, compare the same unobstructed background area across boundaries, including dark, middle and bright tones. If a whole-image luminance/contrast jump exists, match luminance to a stable accepted interval and recheck both joins. Avoid independent RGB gain changes that introduce hue/contrast shifts. Do not normalize intentional lighting changes, camera moves or unrelated scenes.
- `scripts/match_lighting.py` provides the luminance quantile method used successfully on Water Fox. Select a verified stable background rectangle excluding creature, reflections and moving water; do not assume the top of every frame is static. It writes a new export plus a correction report, preserves optional audio, and decodes the result. Example (normalized rectangle and reference seconds are project-specific):

```powershell
python scripts/match_lighting.py --input ASSEMBLY.mp4 --output NEW_VERSION.mp4 --region 0 0 1 0.42 --reference 5.5 6.5
```

- Do not freeze an entire background by default. Where a fixed plate is suitable and authorized, keep natural motion where needed and verify a mask against the subject's complete trajectory, ears, tail, droplets and shadows. A mask tied only to the platform can erase the subject beyond its edge. Use feathering outside the subject, not across its body.
- For a wide walk, describe actual translation, route radius and safe platform limits in the prompt; camera motion does not substitute for walking. New motion or a regenerated ending is a creative/generation change requiring authorization. When authorized, start the ending from the actual last frame of the accepted walk.

Make one reasoned correction pass and inspect it before review. If artifacts persist, change the local approach rather than repeatedly increasing blend duration or automatically regenerating clips. Preserve prior accepted media. Show the finished candidate once for explicit acceptance; finishing does not waive clip/frame/final review gates or publication approval.

Use `scripts/finalize.py` for the final assembly/optional lighting/playback verification/delivery pass; see commands.md. Configure and inspect justified joins first, then inspect the finished boundary windows. Avoid separate encodes and copies when finalize covers the operation.
