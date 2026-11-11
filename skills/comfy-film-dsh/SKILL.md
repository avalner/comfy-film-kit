---
name: comfy-film-dsh
description: ComfyUI MiniMax H3 short-film production inside DeepSeek Harness — generate, review and assemble creature shorts with the portable film.py controller, adapted to DSH tools (no Codex browser panel, no sub-agent delegation, media shown via local player and HTTP links).
---

# ComfyUI films in DeepSeek Harness

This is the DSH counterpart of the Codex `comfy-film` skill. The controller is shared and now lives outside Codex:

`$Tools/comfy-film/`

- `scripts/film.py`, `finalize.py`, `match_lighting.py`, `youtube.py`, `progress.py` (+ `progress.html/js`, `progress-worker.cjs`)
- `assets/machine.json` (Python path, ComfyUI startup), `assets/youtube.json` (channel, playlists)

The Codex skill keeps its `scripts/` and `assets/` as Windows junctions to that folder, so both agents run byte-identical code and there is one place to edit. Always reach the scripts through the resolved `$Tools` and `$py` below — never through a path typed by hand. Never duplicate or fork the controller; this skill only changes the surrounding workflow.

## Paths — resolve once, before the first command

Nothing in this skill text is an absolute path: it uses a handful of variables, and you resolve them
once per session from `paths.json` in the kit root.

| Variable | What it is |
|---|---|
| `$Tools` | this checkout (the kit) |
| `$Comfy` | the ComfyUI portable root, the folder that holds `python_embeded` |
| `$py` | the interpreter: `$Comfy/python_embeded/python.exe` |
| `$Films` | where film projects live |
| `$Series` | the Elemental Creatures series root (only if the user has one) |
| `$Paintings` | the Paintings series root (only if the user has one) |
| `$MediaRoot` | the tree the media preview server serves, so `/watch/...` links resolve |
| `$P` | the whole record, for `$P.ffmpeg`, `$P.ffprobe` |

```powershell
$P         = Get-Content '<kit>\paths.json' -Raw | ConvertFrom-Json   # the one path you type
$Tools     = $P.tools;  $Comfy = $P.comfy;  $py = $P.python
$Films     = $P.films;  $Series = $P.series; $Paintings = $P.paintings
$MediaRoot = $P.media
$film      = "$Tools/comfy-film/scripts/film.py"
```

`install.ps1` writes `paths.json`; it holds `tools`, `comfy`, `python`, `ffmpeg`, `ffprobe`, `films`,
`series`, `paintings`, `media`. If the file is missing, run `install.ps1` — do not guess a drive
letter, and do not run a command whose variables you have not resolved. When you quote a command to
the user, quote it with these values filled in.

## Start of a session

Two questions come before anything creative:

1. **Is the machine ready?** `setup/install-comfy.ps1 -Modes <mode> -Check` — see
   `references/install.md`. `status: ready` means go. `status: missing` means a short conversation
   about modes, disk and time, then an approved install — never a render into a missing model, and
   never a silent download of tens of gigabytes.
2. **Which mode?** `video` (one clip), `long` (chained takes), `refs` (from pictures), `lipsync`
   (under supplied audio) — see `references/modes.md`. Ask this first: it chooses the model set, the
   prompt shape and the thing the reviewer looks at.

`film.py` runs the first three modes; `lipsync.py` runs the fourth. Both read the same
`machine.json` and talk to the same ComfyUI, so the setup is shared.

## What differs from the Codex skill

| Codex instruction | DSH replacement |
|---|---|
| "Show the URL in a Codex browser panel / reuse the browser tab" | `film run` returns a panel URL, but that helper dies with the `run` process. Start the panel yourself as a background job and verify it before posting (`references/progress.md`). Do not try to drive a browser — DSH has no browser tool. |
| "Use the user-input/menu tool" | `ask_user_question` with short explicit options (Принимаем / Нужно изменить / Отклоняем). The links, numbers and any long text go in the chat message **before** the call — see non-negotiable 9. |
| "Delegate prompt and metadata drafting to a cheap sub-agent" | Not applicable. Draft in the parent; delegation.md is intentionally absent. |
| "Save usage snapshots with the account usage-limit tool" | No such tool here. Skip measurement. |
| Implicit trust that the user sees images in chat | They often do not. Write the media to a file and show it the way this GUI can open it — path link for images/documents, `http://127.0.0.1:8199/...` for video. Never `Start-Process`. |

Everything about generation, acceptance gates, assembly and publication carries over unchanged.

## Non-negotiables

1. **Review after every generated clip.** Show the clip, then ask accept / change / reject. Do not continue to the next segment without an explicit answer. Silence is not acceptance.
2. **Keyframes come from one photo.** If the first and last frames show the same background in different states, FL2VA will morph it over ten seconds. Build the second keyframe by editing the first (see `references/artifact-playbook.md`) or start the film from the design frame.
3. **Prompt per the H3 guide.** Read `$Tools/skills/h3-prompt-writing/references/base-en.txt` before writing. Header timecode = real duration to two decimals (243 frames → `10.13`). `[Shot 1]` opens with the style, static camera is `The camera holds a static shot`.
4. **No negative word lists in prompts.** "no swelling, no sprouting, no spikes" seeds those exact concepts. State the positive state instead.
5. **Deliverable naming** — `<name>-final-vN.mp4`, H.264 `yuv420p`, AAC, `+faststart`, decode checked. Use `finalize.py` (under DSH: `scripts/finalize_sandbox.py`).
6. **Publication needs metadata approval** even when the user already said "publish".
7. **Measure a take before you show it.** Run `scripts/motion_profile.py` on every candidate and check a 0.5 s contact sheet for silhouette change. A dead run in the middle means the beat did not happen — fix the prompt. A dead tail is normal for FL2VA — trim it. Never offer a take with a freeze you have already seen for acceptance: show it, say it failed and why, and ask whether to spend another render. The extra render is the user's decision, never the model's — 2026-10-30: "почему самовольно решил делать 3 дубля?" One show-and-ask round per take; no silent retakes, even when the defect is obvious.
8. **A clip ends where its last keyframe is.** If the last frame is the apex of a jump, the model will hang there for a second. Do not lock the apex; or cut the hang in post. The same goes for the still pose at the end of an assembly.
9. **The progress link leaves with the submission, not after it.** The moment `film run` returns, the next chat message must contain the verified panel URL (read `.pipeline/progress-server.json`, check `/api`), the segment number and its duration — and only then may the `wait` background job start. The tool JSON is invisible to the user; a render with no posted URL reads as silence. If the panel is down, restart it and post the new URL; if it cannot start at all, say so and keep the render running. Added 2026-10-30 after the URL was skipped: "что нужно сделать чтобы ты не забывал давать ссылку на прогресс генерации видео". **The panel speaks the language of the chat**: every widget is English by default, so in a Russian conversation set `$env:COMFY_FILM_LANG='ru'` before `film run` (or pass `--lang ru` to `progress.py`, `upscale_progress.py`, `image-progress.py`, `serve-media.py`); `?lang=ru` / `?lang=en` switches a running panel without restarting it.
10. **`ask_user_question` carries the choice, not the content.** Write the clip link, the measured numbers, the full title and description, and the settings into the chat message **before** the tool call; the question field is one short sentence and option labels are two or three words. Text stuffed into the question or into option descriptions is what the user sees instead of the preview — "ты всю информацию мешаешь в самой опции, на которую мне нужно нажать. Лучше пиши эту информацию перед тем как задавать вопрос" (2026-10-30). A long preview — metadata, a description block — goes in the message as a fenced text block, and the card asks only "Публикуем?" with bare labels.
11. **Segment 2 onwards is always `guide+last`, never a fresh start from a board.** `--first <board>` on a later segment is forbidden. Every board is a separate generation, so the subject sits a few percent off between boards; a take that starts from a board lands near it, the next take starts from the same board and drifts the other way, and at the cut the two errors add up into a visible jump in scale and position. `keyframe_check.py` will not warn you — a global mean over a dark sky reads ~3/255 while the eye sees the subject hop. The rule is `--guide prev --guide-frames 22 --last <board>` for every segment after the first (see "Continuation" below). Added 2026-10-31 after a six-take FL2VA film whose joins measured 2.74 / 3.51 / 3.11 / 3.54 / 3.78 drew "видны швы при склейке" on the first watch. A latent chain (`--chain latent`) now exists as a second continuation; measured on the same kind of take it re-generates the overlap (45/255) instead of pinning it, so it does not replace `--guide prev` where the join must be invisible.
12. **The whole film is built to the end at 384×672, and only then re-shot at native.** Pass 1 is a complete previz project (`film preview`): every segment, every beat, trims, joins, the loop close, stitched and watched as one cut until it is approved. Pass 2 generates the same plan again at 768×1344 from the same boards and prompt files, segment by segment, with its own reviews. Never mix the passes — no native take before the previz cut is approved, and no previz take inside the deliverable project. This is a rule, not an optimisation: at 384×672 a 5 s take is ~30 s instead of ~10 min, so a beat the model cannot perform is found in minutes instead of an evening. 2026-11-06: the first beat of `ruler one bent thing` burned six native takes (~50 min) before a previz take reproduced the same failure in 61 s and showed it was the model, not the prompt.
13. **Every render gets a watch link, including tests and previz takes.** Copy the file to a stable path under `outputs/`, post the `http://127.0.0.1:8199/watch/...` URL, and say in the same message what it shows and whether it passed. A take that exists only as a `.pipeline/reviews/` path in tool output is invisible: the user cannot judge it and cannot compare two variants. This applies to cheap 30 s preview takes as much as to native ones — a batch of test takes should arrive as a list of links, one line each, not as a summary of what I concluded from them. 2026-11-06: "ты можешь показать те видео, которые сгенерировал в ходе тестирования. И всегда так делай."
14. **One take per message — never chain renders and present them at the end.** The moment a render lands: copy it, post its link with a one-line verdict, and **stop the turn**. Do not queue the next `add`/`run` before the user has seen the clip. This holds even when the takes are cheap, even when the plan is already approved, and even when the next prompt looks obvious: the user asked to watch the film being built take by take, and a five-clip dump at the end is not that. If the session must keep moving without a reply, say so and offer "без остановок" as an explicit mode the user has to choose — silence is not that choice. 2026-11-06: "а почему не показывал каждый фрагмент после генерации. Я же просил."

## Two-pass production

| | Pass 1 — previz | Pass 2 — master |
|---|---|---|
| Project | `film preview --project MASTER` → `<name> previz 384x672` | the film's own project |
| Canvas | 384×672 (0.26 MP) | 768×1344 (1.03 MP), native |
| Take length | 5 s (~30 s render) for iteration, up to 10 s for a full-beat check | 5–6 s guide continuations, 10 s opening |
| Order | the **entire film**, in order, with trims, joins and the loop close | the same segmentation, in the same order |
| What is approved | staging, timing, whether the model performs each beat, the cut itself | each take's pixels, each join |
| Delivery | never | `finalize_delivery.py` only here |

Rules for the two passes:

- **Same prompt files, same boards, same segmentation.** The previz and the master both `add` from
  `<project>/part-N-*.txt` and the same `00-*.png`; never fork the text, or the re-shoot stops being a
  re-shoot.
- **A guide chain never crosses the passes.** H3 guide clips are bound to the project canvas, so a
  384 take cannot continue a native take. Native takes are generated again from the boards and
  prompts; a seed makes them closer, never identical.
- **Trims carry over as numbers.** Record `trim --head/--tail` per segment on the previz, then apply
  the same values in pass 2 and check the result with `ffprobe` (`fps`, `nb_frames`).
- **If a native take fails a beat the previz performed**, fix it in the previz first (~30 s per try),
  then re-shoot that segment. Never debug staging at native cost.
- **Keep the previz project.** It is the reference cut: it stays on disk with `preview_of` pointing at
  the master, and `film status` labels it as such. Do not delete it once the master is done — it is how
  a later re-cut is judged.
- **Upscaling the previz is not a delivery route.** Measured 2026-11-06 on `ruler one bent thing`:
  384×672 → SeedVR2 ×2 → 768×1344 costs 246 s per 10 s take and matches the native frame count, but at
  1:1 it loses the paper grain, thickens the thin engraved ticks, softens the brass hole and flattens
  the wall bokeh (paper patch detail 82–167 → 32–39 Laplacian variance), and the user rejected it on
  sight for **artefacts along the edges of moving objects**. It is acceptable for a screening copy of
  the previz and nothing else. Delivery is always a native re-shoot.

## DSH-side execution

```powershell
$py   = $P.python      # resolved in "Paths" above
$film = "$Tools/comfy-film/scripts/film.py"
& $py $film status --project '$Films/<name>'
```

Long renders: run `wait` as a background job and collect it with `job_output`; never poll in a loop. A wait timeout never authorizes resubmission.

Media: the DSH sidebar previews images and documents from a **local path**, but **cannot preview video**. Show each type the way it opens, and never use `Start-Process` (stale Windows associations pop a picker dialog).

- Images/documents — markdown link, absolute path in angle brackets, normal text:

```markdown
[keyframes-compare.png](<$Films\<name>\.pipeline\kfcheck.png>)
```

- Video — HTTP link from the shared preview server (start once per session, whole tree):

```powershell
& $py '$Tools/skills/comfy-film-dsh/scripts/serve-media.py' --directory $MediaRoot --port 8199
```

`serve-media.py`, not `python -m http.server`: the stdlib handler ignores `Range`, so the player cannot seek and aborts on every scrub.

Always link `/watch/...`, never the bare file path. Navigating straight to an `.mp4` makes the embedded Browser show its red «The page could not load» banner once per tab; `/watch/` serves an HTML page with a `<video>` element, which loads cleanly.

```
http://127.0.0.1:8199/watch/<project>/outputs/<clip>.mp4
```

Verify `HEAD` = 200 on the `/watch/` URL, and `Range: bytes=0-1023` = 206 on the raw file, before posting. Full rules: `references/media.md`.

Clean up when the film is published: kill the progress-panel background job (and the `pid` in `.pipeline/progress-server.json`) and the preview-server job.

## Review gate — measure, then show

Before every `ask_user_question` about a clip:

1. `scripts/motion_profile.py CLIP` — JSON with 0.5 s motion windows, dead runs (< 0.5), still runs (< 1.2) and a verdict. Every FL2VA clip ends nearly still; the question is whether the still sits where the story needs motion.
2. A 0.5 s contact sheet (`ffmpeg -ss` per step, composite with PIL/cv2). Motion proves something moves; the sheet proves the **pose** changes. A "long preparation" can have plenty of motion and still read as standing in place.
3. Decide before showing:
   - dead tail (last 0.5–1.5 s) → trim in post, never re-render for this;
   - dead or motion-only run in the middle → reject and re-prompt with silhouette-changing action;
   - joins: with `guide+last` the join is a continuation, so compare the last frame of part N with **frame 22** of part N+1 (`keyframe_check.py` or a plain diff) and look at the pair — a shifted subject at ~3/255 is still a visible hop; a board-to-board cut at ~6 that reports "safe" is already a seam.
4. Post the clip link first, then the numbers that shaped the decision — all of it as a chat message. Only then call `ask_user_question` with one short sentence and bare labels; the payload never goes into the question or the option descriptions (non-negotiable 9).

Trims:

- `film trim` sets absolute values and **resets the end you omit to 0** — always pass `--head` and `--tail` in the same call.
- Cut on a multiple of 1/24 s (0.125, 0.25, 0.375, 0.5, 1.0, 1.25 …). 0.42 s silently turns 24 fps into 23.99996 and the export inherits it.
- After a trim: re-`stitch`, check `fps` and `nb_frames` with ffprobe, then `finalize` a **new** version. Never overwrite an approved file; record what changed in `brief.md`.
## Session hygiene — one film, one chat

**New creature → new chat. Never a new chat per part, never the whole series in one chat.**

- A film costs roughly one chat of context: 3–5 takes, each with a prompt draft, a render and a review round, plus assembly and publication. That is the natural unit, and it keeps every rejected take and the reason it was rejected in front of the model.
- One film per part is wrong: parts share continuity, join frames, tempo and the accepted look. Splitting them throws away the decisions that make part N+1 match part N.
- The whole series in one chat is wrong: seven films fit only by compacting, and the compaction summary keeps the artefacts but loses the per-take reasoning — exactly what you need when a background morphs again.
- The chat is not the record. `film.json`, the prompt files, `.pipeline/` and `outputs/` are. Any chat can be dropped without losing a film; that is why the workflow is codified here.
- A film is now **two projects** — the previz twin and the master — and both belong to the same chat. Pass 1 fills the chat with cheap previz takes; keep it, because the reason a beat is staged the way it is comes from there, and pass 2 is a long quiet re-shoot that only makes sense next to it.

What does not cross the chat boundary: background job handles. The ComfyUI process and a running render survive, the job id and its output do not. In the new chat run `film status` first; if a render was in flight, `film recover`. Never resubmit a job you lost track of — the preview server on 8199 also needs restarting, and the port may still be held by the old process.

If a chat must be abandoned mid-film, finish the current take in the same chat and start the next one cleanly.

## Server start

`run`/`start` launch ComfyUI from `startup.argv` in `assets/machine.json` (or the project's own copy in `film.json`). The argv must contain `--disable-auto-launch`; without it ComfyUI opens its UI in the default browser on every start, which is noise during unattended runs. `--windows-standalone-build`, `--listen 127.0.0.1` and `--port 8188` stay as configured — the port must match `config.server`.

When the browser tab does appear anyway, check the flags on the actual process, not in the config:

```powershell
Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -like '*ComfyUI*main.py*' } | ForEach-Object { $_.CommandLine }
```

Existing projects keep their own startup copy in `film.json`; changing `machine.json` affects new projects only.

## Pass 1 in practice — the whole previz film

Pass 1 is a complete film, not a rehearsal of one beat: same segmentation, same order, same trims, same
joins, same loop close, stitched and watched end to end. Only when that cut is approved does pass 2
exist (non-negotiable 12).

```powershell
film preview --project PROJECT                       # '<project> previz 384x672'
film add --project '<project> previz 384x672' --first BOARD.png --prompt-file PART-1.txt --seconds 10
film run --project '<project> previz 384x672'
film add --project '<project> previz 384x672' --guide prev --guide-frames 22 --prompt-file PART-2.txt --seconds 5
film trim / join / stitch --project '<project> previz 384x672'
```

`preview` copies the master's `workflow-api.json`, bindings and config, overrides only the canvas and
the default take length (384×672, 5 s), and records `preview_of` in the new `film.json`. It is
idempotent: if that folder already has a `film.json` it reports `status: exists` and changes nothing.
`film status` labels a previz project as staging-only, so a preview file can never be mistaken for a
deliverable.

Measured on `ruler one bent thing`, same board and prompt, turbo 8:

| Canvas | Area | Take | Wall time |
|---|---|---|---|
| 768×1344 (native) | 1.03 MP | 10 s / 243 f | ~600 s |
| 384×672 | 0.26 MP | 10 s / 243 f | 61 s |
| 384×672 | 0.26 MP | 5 s / 124 f | 29–31 s |
| 320×576 | 0.18 MP | 5 s / 124 f | 36 s (first run, model load) |
| 256×448 | 0.11 MP | 5 s / 124 f | 21 s |

Notes that follow from how H3 works:

- **A preview is not footage.** The guide clip is bound to its project's canvas, so a 384 take can
  never continue a native take, and a native take can never continue a preview. Pass 2 generates again
  from the same boards and prompt files — a seed helps, it does not reproduce the motion. Approving the
  previz approves the *cut*, never the pixels.
- Keep one prompt file per beat, shared by both passes, so the re-shoot cannot drift from what was
  approved. Iterate the text in pass 1 only.
- 384×672 keeps the exact 0.5714 portrait ratio; 320×576 and 256×448 do not (0.556 / 0.571), so framing
  differs slightly — compare staging only at 384.
- Below 384 the face and material detail stop being judgeable; 256×448 is for "does it move and where"
  only. Never deliver a preview canvas.
- Run the whole review gate on previz takes too (`motion_profile.py`, contact sheet, drift), with one
  exception: a preview take is cheap enough that a clear failure may be re-run inside the same round
  after reporting it, provided the user has already authorised iterating on that beat.


## Prep and checks

- `scripts/prompt_lint.py` — flags negative lists, wrong timecode format, missing style line, missing static-shot phrase, missing fields. Run it on every prompt before `add`.
- `scripts/keyframe_check.py` — compares two stills and reports the background difference that will turn into a morph; run it before any FL2VA where both frames exist.
- `scripts/motion_profile.py` — per-0.5 s motion, dead/still runs, verdict; run it on every candidate before review and on the finished assembly to confirm the trims.
- `scripts/finalize_sandbox.py` — same arguments as `finalize.py`, safe under the DSH workspace-write sandbox (see `references/commands.md`).

## Continuation — `guide+last` for every segment after the first

**The default for every film in this series, not a choice to make per shot:** segment 1 is generated
from the boards; every later segment continues the previous clip.

```powershell
film add --project PROJECT --guide prev --guide-frames 22 --last BOARD-NEXT.png --prompt-file PART-N.txt --seconds 6
```

A take that starts from a board does not *land* on it — it eases into it and stops a few values short.
The next take starts from that same board and drifts in another direction. At the cut the two misses
add up: the subject changes size and position in one frame while the sky stays put. That is the seam,
and a whole-frame difference cannot see it, because the dark background dominates the mean.

`--guide prev` feeds the previous clip's last 22 frames through `MiniMaxH3AddGuide` at frame 0, so the
take starts on the previous clip's actual pixels and the join is the next frame of the same motion.
`--last` then pulls it onto the designed pose. `add` marks the 22 guide frames for a head trim, so the
stitch begins on the first generated frame after the previous clip's end.

Rules that go with it:

- 22 guide frames (0.9167 s). The first *shown* frame of the take is frame 22.
- 5–6 s per take. On H3's 17k+5 grid 5 s → 124 frames (5.17 s), 6 s → 158 frames (6.58 s). Do not go
  past ~6.6 s: camera, framing and character detail drift.
- Make the last frame a settled pose. `--last` is what stops the chain from wandering; without it a
  long continuation invents its own ending.
- **Trim the tail before you feed the guide.** The tail trim defines which 22 frames become the next
  take's guide. If the take is still decelerating into its `--last` pose, cutting inside that
  deceleration bakes a pause into the chain: the shown end runs at 0.1–0.5 motion and the next take
  lands 2.6–3.3 away in one frame — a stop, then a skip. Cut on a frame that still carries motion.
  If it is already baked in, `film join --after N --mode crossfade --seconds 0.25` on every boundary
  turns the stop-and-jump into a continuous ramp (verified 2026-10-31).
- The prompt header changes — no Picture 1, the guide is the start:
  `How the reference pictures align with the target video — the 22-frame guide clip plays from the
  0.00-second mark; Picture 2 aligns with the S.SS-second mark of the target video.`
  Then describe style, scene and characters in full (there is no first image to lean on), state what
  the guide clip ends on and that the take carries that motion straight on, and time the beats from
  `00:00.92` in `MM:SS.ss` form. Working example:
  `$Series/extreme sunflower/part-3-guide-last-prompt.txt`.
- **The final segment cannot use `--loop`** — it does not combine with `--guide`. Extract the opening
  frame instead and pass it as `--last`:

  ```powershell
  film extract --project PROJECT --segment 1 --which first --scale 1
  film add --project PROJECT --guide prev --guide-frames 22 --last frames/segment-0001-first-1x.png --prompt-file FINAL.txt --seconds 6
  ```

  The loop then closes on the exact frame the film starts with.
- **Check the join on the shown frames**, not on the board: last frame of take N against frame 22 of
  take N+1. Look at both stills side by side; a number under 4 can still hide a shifted subject.

### Re-shooting an accepted segment

`film reject` only accepts a candidate in `review`; an accepted segment cannot be rejected through the
CLI, and `accept` refuses to overwrite an existing `clips/segment-000N.mp4`. To rebuild a chain:

1. Copy `film.json` to `.pipeline/film-vN-record.json` (the full record of the old cut).
2. Move `clips/segment-000N.mp4` for every rebuilt segment into `.pipeline/takes-vN/`.
3. Truncate `segments` to the last good one, clear `joins` and `exports`, write `film.json` back.
4. `film add` the new segments with `guide+last`, and record the rebuild and the reason in `brief.md`.

Do this only when no render is in flight, and never delete the archived takes.


## Delivery (one command, upscale on by default)

`finalize_delivery.py` is the standard close for a film: it runs the controller's `finalize.py`
(same arguments, safe temp dir) and then the ×2 SeedVR2 3B FP16 delivery upscale, copying both files to
the deliver directory.

```powershell
$py '$Tools/skills/comfy-film-dsh/scripts/finalize_delivery.py' `
    --project PROJECT --name NAME --deliver-dir OUTPUTS
```

- Outputs `<name>-final-vN.mp4` and `<name>-final-vN-2x.mp4` (1216×2112 from a 608×1056 film), H.264
  CRF 16, audio copied, `+faststart`, decode verified, source untouched, no overwrite.
- `--no-upscale` skips the second file; `--scale 3` upscales ×3. The upscaler lives outside ComfyUI
  at `$Tools/realesrgan/` (ncnn Vulkan, `realesr-animevideov3`); 480 frames take
  ~42 s plus the encode.
- The upscale is cosmetic sharpening: it does not restore detail the VAE never encoded, and the
  motion profile stays identical (verified on v5-2x — no flicker). For real detail start the project
  at 768×1344 (H3 native portrait) so the whole continuation chain shares that canvas.
- Check one 1:1 crop against the source before showing the result; `animevideov3` keeps clean 3D
  renders smooth, `x4plus` can crunch pollen and fine texture.

## Post-production (installed, use when a take needs surgery)

ComfyUI has three extra node packs; restart the server after any change and verify the nodes appear in `/object_info`.

- **RIFE VFI** — smooth speed change and slow motion. Interpolate ×2 to 48 fps, then `setpts/1.3 + fps=24`, instead of duplicating frames. Tested workflow: `assets/workflows/rife-2x.json`.
- **ProPainter** — remove an object the generation refused to drop (stuck beads, an extra crumb, a popping moss patch) by masking it and rebuilding the area from neighbouring frames.
- **VideoHelperSuite** — video/mask IO for both of the above.

Full recipes, parameters, mask commands and caveats: `references/post-tools.md`. Neither tool replaces a regeneration for story or pose problems.

## References

- `references/install.md` — installing ComfyUI, nodes, models and FFmpeg on a bare machine
- `references/modes.md` — video / long / refs / lipsync: what each one is, asks for and needs
- `references/setup.md` — new-project questions and canvas profile
- `references/commands.md` — CLI syntax (film.py, lipsync.py)
- `references/assembly.md` — joins, continuity finishing, lighting match
- `references/youtube.md` — publication and verification
- `references/progress.md` — panel behaviour in DSH
- `references/media.md` — how to show clips and stills to the user
- `references/post-tools.md` — RIFE speed change, ProPainter object removal
- `references/series-elemental-shorts.md` — the Elemental Creatures series profile
- `references/artifact-playbook.md` — what to do when the model misbehaves
