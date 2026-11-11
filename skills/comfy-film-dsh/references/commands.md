# CLI reference

The controller lives at `I:/Video Generation/Tools/comfy-film/` (the Codex skill reaches the same
files through junctions). Use Python from `I:/Video Generation/Tools/comfy-film/assets/machine.json`
with `I:/Video Generation/Tools/comfy-film/scripts/film.py`. `film` below is shorthand for that
invocation; `finalize.py`, `match_lighting.py`, `progress.py` and `youtube.py` sit next to it.
Every command outputs a compact JSON object; failures have nonzero exit codes.

## Start and continue

```powershell
film init --project PROJECT --title 'Moon Garden' --width 608 --height 1056
film doctor --project PROJECT
film add --project PROJECT --first START.png --last END.png --prompt-file PART1.txt --seconds 10
film run --project PROJECT
film wait --project PROJECT --timeout 7200
```

`run` submits once and returns. `wait` is a quiet long-running local process: await the SAME terminal session in waits of up to 50–60 seconds. No repeated model-level status checks are needed. On timeout, wait again; do not rerun. H3 rounds requested duration to its 17k+5 frame grid: 10 seconds normally produces 243 frames (10.125 s); 15 produces 362 frames (15.083 s).

After showing the candidate and receiving explicit acceptance:

```powershell
film accept --project PROJECT --segment 1
film extract --project PROJECT --segment 1 --which last --scale 2
film add --project PROJECT --last PART2END.png --prompt-file PART2.txt --seconds 15
film run --project PROJECT
film wait --project PROJECT
```

Omitting --first on a later clip automatically extracts the preceding accepted clip's last frame, upscales 2x without redrawing and uses it. Omit --last for first-frame-only continuation. Use --loop instead of --last for a final clip ending on the actual first frame of the first accepted clip. An explicit --first can start an intentional new scene. Both references are identically cover-cropped to the selected canvas: choose a canvas close to the intended composition to avoid cropping important content.

- **`--chain latent`** (see below) is the third way to continue: the previous sampler's latent.
- Without `--guide`, a later take starts from the previous clip's extracted last frame — a still pose,
  which is what a beat that must continue motion does *not* want.

## Latent chain (`--chain latent`)

The workspace's method, ported: instead of feeding the previous clip back as decoded frames, a take
starts from the previous sampler's saved latent tail (17 tokens), concatenated to its own conditioning
latent and cut back to length, so clips join end to end.

```powershell
film add --project PROJECT --chain latent --prompt-file PART-2.txt --seconds 6
```

- **No keyframes**: `--first`, `--last`, `--loop` and `--guide` are refused. The scene is described by
  the prompt; the first take of a film still needs its board.
- Every take saves `tail.latent` (17 tokens, ~1.6 MB) next to its candidate, so any accepted take can
  be chained later.
- The take generates `kept + overlap` frames and keeps `kept`. The overlap snaps to H3's 17k+5 grid:
  for a 5 s take at the default `--chain-overlap 0.9`, 34 frames (1.4 s) are generated twice and cut.
- Kept plus overlap must stay at or under 15 s.
- Measured 2026-11-11, 384x672, 5 s, fast route: the overlap is **regenerated, not pinned** — the
  first shown frame of take 2 differed from the last frame of take 1 by 45/255 mean, and no frame of
  take 1 matched it. The mask passes `SetLatentNoiseMask` → `LTXVConcatAVLatent` without error, so
  this build does not hold the masked region through `SamplerCustomAdvanced`. The chain buys motion
  context (the sampler starts from the previous latent instead of noise), not a pixel-exact join.
- For a seam-free join keep `--guide prev --guide-frames 22 --last board.png`. Use `--chain latent`
  when the scene should *evolve* into a new beat rather than continue the same one.

## References (Ref2VA)

```powershell
film add --project PROJECT --ref2va hero.png --ref2va room.png `
    --ref2va-model minimax_h3_ref2va_pruned_int8_convrot.safetensors `
    --ref2va-lora minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors `
    --ref2va-steps 6 --ref2va-size match `
    --first BOARD.png --prompt-file PART1.txt --seconds 8
```

- `--ref2va IMAGE` is repeatable, 1–9 pictures; they are copied into the segment folder.
- `--ref2va-model` swaps the diffusion model for this take only. Without it the project's FL2VA
  model runs the Ref2VA graph, which it was not trained for.
- `--ref2va-lora` + `--ref2va-steps 4–8` is the turbo path (the graph switches to `euler` and sets
  a sigma shift); 20–25 steps without a LoRA.
- `--ref2va-size max` preserves reference detail and is much slower; `match` fits them to the canvas.
- The take still carries `--first`, `--last` or `--guide`: references describe *who*, keyframes fix
  *where*. `add` reports the combination as `ref2va+i2va`, `ref2va+fl2va`, `ref2va+guide+last`.

## Lipsync

```powershell
$py 'I:/Video Generation/Tools/comfy-film/scripts/lipsync.py' `
    --audio voice.mp3 --ref face.png --prompt-file LIPSYNC.txt `
    --project 'I:/Video Generation/Projects/<film>' [--scale 2] [--width 768 --height 1344]
```

Separate entry point, same `machine.json`. Length follows the audio (`--seconds` only cuts it
shorter). Writes `clips/lipsync-000N.mp4` and a journal record under `.pipeline/lipsync/`.
`--dry-run` builds and validates the graph without queueing; `--unet/--lora/--clip/--video-vae/
--audio-vae/--upscaler` override the names resolved from ComfyUI. Single take only — the audio lock
is per take, so it cannot be chained with `--guide`.

## Continuation (H3 `AddGuide`)

**Every segment after the first is generated this way.** Boards are separate generations and their
few-percent drift turns a board-to-board cut into a visible seam; the continuation starts on the
previous clip's real pixels instead. Use `--guide prev` **with** `--last` (the board the beat must
land on). Bare FL2VA on a later segment is not an option.

```powershell
film add --project PROJECT --guide prev --guide-frames 22 --last BOARD-NEXT.png --prompt-file PART-N.txt --seconds 6
film run --project PROJECT --segment 3
```

- `--guide prev` takes the last `--guide-frames` frames of the previous **accepted** clip (honouring
  its `trim_tail`); `--guide PATH` continues any other clip. Allowed counts are 5, 22 or 39 frames
  (H3's 17k+5 clip grid); 22 frames ≈ 0.92 s.
- The guide is copied to `.pipeline/segments/NNNN/guide-source.mp4` and fed through
  `VHS_LoadVideoPath` → `MiniMaxH3AddGuide` at frame 0, with its soundtrack anchored too.
- `add` sets `trim_head = frames / fps` automatically, so the duplicated guide frames are cut at
  stitch and the new segment starts on the first generated frame after the previous clip's end.
- No `--first` or `--loop` with `--guide`, but **`--last` is allowed and useful**: the guide carries
  the motion in and the last keyframe pulls the take to a designed pose. Verified 2026-10-31:
  guide + board 04 as `--last`, 5 s → the end frame matches the board at 6.32/255 and the fall is
  continuous. At 8 s the same pair made the model resolve the two anchors with an unnatural arc
  (the trio shot up into the sky, motion 25, then came down), so keep anchored continuations to
  5–6 s and make the last frame a *settled* pose, not another airborne one. The prompt still needs
  the full style/character/scene description, plus a line that the guide clip plays from 0.00 s and
  the take continues its motion while converging on the final still.
- Verified 2026-10-31: the guide reproduces frame-for-frame (5.72/255 on frame 0, 6.20/255 on the
  last guide frame), and the first generated frame continues the motion. Long continuations drift:
  camera, framing and character detail can change after ~4 s, so keep an eye on a 0.5 s contact
  sheet and prefer 5–8 s over 10 s.

Project examples: `I:\Video Generation\Projects\Moon Garden` or `I:\Video Generation\Elemental Creatures\ember salamander`. Keep all parts of one film in one project, not a new project per segment.

## Adapters (LoRA) per take

```powershell
film loras --project PROJECT                       # what ComfyUI sees
film run --project PROJECT --segment 1 --lora pika_h3_flex_fl2va_v1_bf16.safetensors
film run --project PROJECT --segment 1 --lora FILE --lora-strength 0.7
film run --project PROJECT --segment 1 --no-lora    # drop the recorded adapters
```

`--lora NAME` (repeatable) inserts a `LoraLoaderModelOnly` node between the quality switch and the
sampler, so it stacks on top of the turbo 8-step LoRA and applies on every path (I2VA, guide,
Ref2VA). A path is reduced to its filename; the name is checked against the live
`/object_info/LoraLoaderModelOnly`, so a typo fails before anything is queued. The chosen adapters are
recorded on the segment in `film.json` (`adapters: [{name, strength}]`), and a re-run after `reject`
reuses them unless `--no-lora` is passed; the submitted graph keeps them as `film-adapter-01`,
`film-adapter-02` in `workflow-*.json`.

Measured on `ruler one bent thing` segment 1, same prompt and board, `pika_h3_flex_fl2va_v1_bf16` at
1.0 against the plain turbo 8-step take: motion energy 2.46 → 2.90 mean and 9.0 → 18.1 peak
frame-difference, detail (Laplacian variance) 371 → 409, camera drift unchanged at ≤1 %, but two
interior dead runs appeared (2.5–3.0 s, 4.5–5.0 s) and the character wandered in position and scale
inside the fixed shot. It is a more elastic performer, not a more controllable one — keep it off by
default.

## Preview (pass 1: the whole film at 384×672)

```powershell
film preview --project PROJECT                       # '<project> previz 384x672'
film preview --project PROJECT --name PLAN-A --width 256 --height 448 --seconds 5
```

Pass 1 is the **entire film** at 384×672 — every segment, in order, with trims, joins and the loop
close, stitched and approved as one cut. Pass 2 (the film's own project, 768×1344) starts only after
that cut is approved, and rebuilds the same segmentation from the same boards and prompt files. Never
generate a native take while the previz is still in flux, and never put a previz take in the
deliverable project.

`preview` creates a sibling project that copies the master's `workflow-api.json`, bindings and config
and overrides only `width`/`height` (default 384×672) and `segment_seconds` (default 5). Records
`preview_of: <master path>`; `film status` then labels the project as staging-only. Idempotent: an
existing previz folder is reported as `status: exists` and left alone.

Cost on `ruler one bent thing` (turbo 8, same board/prompt): 768×1344 10 s ≈ 600 s; 384×672 10 s = 61 s;
384×672 5 s = 29–31 s; 256×448 5 s = 21 s. A preview canvas cannot be chained into a native project —
H3 guide clips are bound to their project resolution — so the previz approves the cut, not the pixels,
and every master take is generated (and reviewed) again.

## Configuration

`init --server http://HOST:8188 --ffmpeg PATH --ffprobe PATH` overrides machine defaults. Supply a custom **API-format H3 graph** with --workflow PATH; graphical nodes/links exports are rejected. --bindings JSON identifies generator/save/first/last node IDs when automatic discovery is ambiguous. This controller targets MiniMaxH3ImageToVideo, not every ComfyUI model family.

The current template needs the installed H3 model files, Qwen encoder, video/audio VAE and turbo LoRA. `doctor` checks node classes, FFmpeg and optional libraries without loading models. Existing projects keep their own config in film.json; changing machine.json affects new projects only.

## Review, resume, recovery

One take per message: after `wait` returns, copy the clip to `outputs/`, post the link with a one-line
verdict and stop — start the next `add`/`run` only after that.

```powershell
film status --project PROJECT
film status --project PROJECT --segment 2
film inspect --project PROJECT --segment 2
film reject --project PROJECT --segment 2 --reason 'The head changes identity'
film run --project PROJECT --segment 2 --prompt-file REVISED.txt
film wait --project PROJECT --segment 2
```

`inspect` returns paths to four-frame overview and ending contact sheets. Do not generate/read sheets by default when the user's video review is sufficient. `accept` copies the approved candidate to clips/segment-NNNN.mp4; it refuses to overwrite accepted clips. The next clip cannot be added or run until the previous clip is accepted.

`run --seed INTEGER` gives an explicit reproducible noise seed; otherwise each authorized attempt gets a new one. A busy ComfyUI queue causes refusal unless --enqueue is explicitly passed. No other jobs are interrupted.

If status is submitting, a response may have been lost after the server accepted the job. `recover --project PROJECT --segment N` searches queue/history by a unique output prefix WITHOUT resubmission. If no unique match is found, inspect server history manually. Never reset state and blindly retry. A remote generation continues after a local wait/network timeout.

Locks normally clear automatically. `unlock --project PROJECT` clears a stale lock only if its owner process no longer exists. It refuses to interfere with a running controller. Cleared server history or a ComfyUI restart may require manual recovery.

## Existing clips and assembly

```powershell
film import --project PROJECT --file EXISTING.mp4
film accept --project PROJECT
```

Repeat for any number of existing clips, whose durations are unrestricted. Imports are candidates until explicitly accepted. Original files remain intact.

```powershell
film trim --project PROJECT --segment 1 --tail 0.75
film trim --project PROJECT --segment 2 --head 0.125 --tail 0    # both ends, always
film join --project PROJECT --after 1 --mode optical --seconds 0.25
film join --project PROJECT --after 2 --mode cut
film stitch --project PROJECT
```

`trim` sets absolute head/tail amounts, not cumulative cuts; zero resets. **An omitted end is
reset to zero**, so a `--head` call wipes a previously set `--tail` and the other way round —
always pass both in one call:

```powershell
film trim --project PROJECT --segment 2 --head 0.25 --tail 1.25
```

Cut on a multiple of 1/24 s (0.125, 0.25, 0.375, 0.5, 1.0, 1.25 …). A time like 0.42 s is not a
whole frame, and the stitched export inherits `23.99996` fps instead of `24`. After stitching,
check `fps` and `nb_frames`; a mismatch means the trim grid was wrong — fix the trim, do not
re-encode the symptom.

Trims are for timing only: a dead tail, a hang at a locked last frame, an over-long pause. A
beat that never happened is a prompt problem — re-prompt, do not trim around it.

`join --after N` configures boundary N to N+1. Default cut preserves a genuine scene change. Crossfade blends moving windows; optical uses bidirectional DIS flow and needs NumPy/OpenCV. Optical flow can distort faces, smoke or large motion. Prefer moving a trim point or reverting to a cut when a morph is worse.

Each transition overlaps windows and reduces total duration by its overlap. Interior clips need room for both joins. `stitch --output PATH` selects a destination; existing exports are never overwritten. Default outputs get unique names. All clips must be accepted.

Video is normalized with aspect-preserving fit/pad, fixed fps and stereo 48 kHz audio. Silent inputs get a silent audio track. Per-clip processing and bounded transition buffers support long films, but intermediate files need free disk space. No auto-deletion of .pipeline caches. Music mixing and arbitrary multitrack editing are outside this controller.

## Dependencies/tests

Python 3.10+, Pillow, FFmpeg/FFprobe. Optical joins additionally need NumPy and opencv-python-headless. These are already available in this machine's configured Python. No OpenAI API key is used by the controller.

Standalone toolkit tests: `python tests/test_pipeline.py`. They use a local fake API and tiny synthetic clips, never actual GPU generations. They check acceptance gates, submission/recovery, continuation frames, matched input geometry, multiple clips, missing audio and join modes.

Status returns counts and only the latest five segments by default to keep long-film context small. Use --segment N for one older segment; full state remains in film.json.

## New-project settings

At skill activation for a new project, ask only for missing settings using setup.md. CLI: init --quality turbo|standard|workflow --seconds 10|15 --audio generated|silent --music none|generated|later. Width/height set the canvas. Turbo uses the bundled 8-step branch; standard uses its 20-step branch. workflow preserves a custom graph. Later add commands inherit the saved duration. Music selection is saved for prompt writing; --audio silent omits the output audio track. It does not bypass H3 joint latent computation.

## Automatic ComfyUI startup

run, doctor, start, recover and an active wait check readiness. If local ComfyUI is offline, the configured executable is launched without a visible window and stdout/stderr go to startup.log_dir. Wait on the same terminal process while it starts. An existing healthy server is reused. A cross-project startup lock prevents concurrent controllers from launching duplicates. Startup process records avoid a duplicate after a startup timeout. Existing projects without startup config inherit machine defaults only if the server URL matches.

`film start --project PROJECT` starts/checks the server explicitly, without submitting a generation. It is normally unnecessary before run. Configuration lives in machine.json startup: enabled, server, argv (argument array, no shell command), cwd, log_dir, timeout (seconds). Set enabled=false to require manual startup. Remote servers are never started on this computer. Configure startup.server and the command port together. No browser or console is opened and no existing ComfyUI process is killed. A startup failure reports the log path and stops. Restarting a stopped ComfyUI does not recover lost GPU jobs/history; inspect an interrupted generation before retrying it.

## One-command final processing

After inspecting continuity and configuring justified trims/joins:

```powershell
python scripts/finalize.py --project PROJECT --name autumn-leaf-fawn --deliver-dir OUTPUTS
```

Uses only accepted clips via `stitch`. Alternatively pass `--input FINISHED_CANDIDATE.mp4`. Optional `--version v2` selects a new unused version; omission chooses next unused vN. Output is always `<name>-final-vN.mp4`, with no extra suffix. Refuses overwrite. For justified lighting correction add `--region X0 Y0 X1 Y1 --reference START END`; use a verified stable background and accepted reference interval. Honors project FFmpeg/FFprobe settings.

Ensures H.264 yuv420p, AAC when audio exists and faststart, copies already compatible video without re-encoding, verifies dimensions/frame count and full decode, retains intermediates and a compact `.pipeline/finalize-*/report.json`. Copies the same finished bytes to OUTPUTS. Show the resulting file for explicit review; success does not mean acceptance or publication authorization.

The output goes to the **project root** (`<project>/<name>-final-vN.mp4`); `--deliver-dir` gets a
copy of the same bytes. Do not look for the deliverable in `outputs/`.

Under the DSH workspace-write sandbox `finalize.py` fails: `tempfile.mkdtemp` creates a work
directory under `.pipeline` whose DACL denies writes even to its creator, so the inner `stitch`
or `ffmpeg` step dies with "Permission denied". Use the skill wrapper — same arguments, same
controller code, only the temp-directory creation differs:

```powershell
$py 'I:/Video Generation/Tools/skills/comfy-film-dsh/scripts/finalize_sandbox.py' `
    --project PROJECT --name autumn-leaf-fawn --deliver-dir OUTPUTS
```

**Standard close: `finalize_delivery.py`** — same arguments plus the ×2 SeedVR2 3B FP16 delivery upscale
and the copy of the upscaled file into the deliver directory. Upscaling is on by default; use
`--no-upscale` to produce only the source-resolution export, `--scale N` for another factor.

```powershell
$py 'I:/Video Generation/Tools/skills/comfy-film-dsh/scripts/finalize_delivery.py' `
    --project PROJECT --name autumn-leaf-fawn --deliver-dir OUTPUTS
```

If a version already exists the script refuses; pass `--version vN` or delete nothing — make a new
version and say what changed.

## Delivery upscale (SeedVR2 3B FP16, outside ComfyUI)

```powershell
$py 'I:/Video Generation/Tools/skills/comfy-film-dsh/scripts/upscale_seedvr2.py' `
    --input PROJECT/<name>-final-vN.mp4 --output PROJECT/<name>-final-vN-2x.mp4 [--scale 2] [--crf 16]
```

- Installed CLI: `ComfyUI/custom_nodes/ComfyUI-SeedVR2_VideoUpscaler/inference_cli.py`; models: `ComfyUI/models/SEEDVR2` (3B FP16 + FP16 VAE).
- The delivery helper processes temporally overlapping batches, streams chunks of 65 frames to PNG, then encodes H.264 yuv420p with AAC and faststart at the source FPS. It verifies frame count, exact scaled dimensions and full decode; the native export is preserved.
- Defaults: batch size 5, overlap 1, CPU model offload and VAE encode/decode tiling. `--batch-size` and `--chunk-size` are helper options for hardware tuning. No automatic fallback to Real-ESRGAN.
- SeedVR2 can synthesize detail and change appearance; review the completed film in motion. Keep guide clips native. Free loaded models on an idle ComfyUI server before running; never interrupt queued/running jobs.

## Checking a candidate before review

```powershell
$py 'I:/Video Generation/Tools/skills/comfy-film-dsh/scripts/motion_profile.py' CLIP.mp4
```

Prints 0.5 s motion windows, `dead_runs` (< 0.5), `still_runs` (< 1.2) and a verdict. Every FL2VA
clip eases into its last frame, so a dead *tail* is expected — trim it. A dead run in the middle
means the beat did not render. Pair it with a 0.5 s contact sheet: motion says something moved,
the sheet says whether the silhouette changed (a "long preparation" can wiggle in place).

`keyframe_check.py FIRST.png LAST.png` remains the tool for comparing two stills or two join
frames; ~6 mean difference is codec noise and a safe cut.
