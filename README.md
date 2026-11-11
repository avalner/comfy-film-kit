# comfy-film-kit

Tooling and agent skills for making short films locally with **ComfyUI** and the
**MiniMax H3** video model (FL2VA / I2VA / guide continuation, 24 fps, native stereo audio).

This is the layer that turns a bare ComfyUI install into a repeatable film pipeline:
keyframes → takes → review → trims → joins → export → upload. It is deliberately
small — one controller, a handful of check scripts, four skills and two optional
upscalers — and every rule that experience paid for is written into the skills
instead of living in somebody's head.

The same scripts drive two different agents on the same machine: **Codex** and
**DeepSeek Harness (DSH)**. Both call the identical `film.py`; only the surrounding
tool names differ (a browser panel versus an HTTP preview server, a menu tool versus
`ask_user_question`).

---

## What is in here

| Path | What it is |
|---|---|
| `comfy-film/scripts/film.py` | The controller. Owns the project record, the ComfyUI job, the guide/continuation graph, trims, joins, stitching and the CLI. |
| `comfy-film/scripts/lipsync.py` | The audio-driven mode: MiniMax H3 Ref2V + native audio lock, two passes, one take. |
| `setup/install-comfy.ps1` | Installs ComfyUI, node packs, models per mode and FFmpeg on a bare machine; `-Check` reports without downloading. |
| `setup/catalog.json` | The installer's data: ComfyUI build, pinned node commits, model URLs/sizes, mode→model mapping. |
| `comfy-film/scripts/finalize.py` | Turns an accepted assembly into `<name>-final-vN.mp4`: H.264 `yuv420p`, AAC, `+faststart`, decode verified. |
| `comfy-film/scripts/progress.py` | Local progress panel (`--serve`) for long renders. |
| `comfy-film/scripts/youtube*.py` | Direct OAuth upload, playlist management, metadata. No browser upload, no intermediary service. |
| `comfy-film/scripts/match_lighting.py` | Measures and corrects a luma match between joined clips. |
| `comfy-film/scripts/film.cmd` | Windows launcher for the controller. |
| `comfy-film/assets/workflow-api.json` | API-format H3 graph the controller binds onto. |
| `comfy-film/assets/machine.example.json` | Machine profile template — Python, ComfyUI startup, FFmpeg. |
| `comfy-film/assets/youtube.example.json` | Channel profile template. |
| `comfy-film/tests/test_pipeline.py` | Ten tests against a fake ComfyUI API. No GPU, ~13 s. |
| `skills/comfy-film-dsh/` | Skill for DeepSeek Harness: workflow, gates, references, and the check scripts (`motion_profile.py`, `keyframe_check.py`, `prompt_lint.py`, `serve-media.py`, `finalize_delivery.py`, SeedVR2 upscale). |
| `skills/comfy-film/` | Skill for Codex. Same controller, Codex-shaped instructions. |
| `skills/living-paintings/` | A separate genre skill: a camera approaches a framed painting, the scene comes alive, the camera pulls back. |
| `skills/h3-prompt-writing/` | The prompt format itself: `references/base-en.txt` and `ref-en.txt`. Read before writing any substantive H3 prompt. |
| `seedvr2/` | SeedVR2 3B FP16 delivery upscaler (runs outside ComfyUI, through its own launcher). |
| `realesrgan/` | Optional Real-ESRGAN ncnn pass for cosmetic sharpening. Binaries are not committed — see `realesrgan/README.md`. |
| `docs/ru/operations.md` | Russian ops notes: interpreter, restart flags, junction rules, how to verify after an edit. |

## Requirements

- **Windows 10/11.** Everything here is written for PowerShell and NTFS junctions.
- **ComfyUI portable** with the MiniMax H3 stack installed: `MiniMaxH3ImageToVideo`, the H3 model files, the Qwen text encoder, video/audio VAE and the turbo LoRA. The kit does not ship models and does not install ComfyUI.
- **FFmpeg and FFprobe.** Any recent build; the machine profile points at them.
- **NVIDIA GPU.** Native 768×1344 takes are heavy: a 10 s take is roughly 10 minutes on a 4090.
- **Python 3.12/3.13.** Use the `python_embeded` that ships with ComfyUI portable — there is no separate environment to maintain.

Optional ComfyUI node packs the post-production recipes rely on: `ComfyUI-VideoHelperSuite`, `ComfyUI-Frame-Interpolation` (RIFE) and `ComfyUI-ProPainter`. SeedVR2 needs `ComfyUI-SeedVR2_VideoUpscaler` plus its 3B FP16 weights.

## Install

```powershell
git clone https://github.com/avalner/comfy-film-kit.git "I:\Video Generation\Tools"
powershell -ExecutionPolicy Bypass -File "I:\Video Generation\Tools\install.ps1"
```

`install.ps1` does three things:

1. Creates `comfy-film/assets/machine.json` from `machine.example.json`, substituting your ComfyUI root.
2. Links `skills/*` into the agent skill folders (`%USERPROFILE%\.dsh\skills`, `%USERPROFILE%\.codex\skills`) as NTFS junctions, so the repository stays the single editable copy.
3. Reports anything it skipped. Nothing is overwritten without `-Force`.

Point it elsewhere with `-ToolsRoot`, `-ComfyRoot`, `-DshSkills`, `-CodexSkills`, `-SkipCodex`.

### Porting to another machine

The skills refer to the canonical location `I:\Video Generation\Tools` because that is
where this kit is developed. If you clone somewhere else, either keep the folder at that
path, or change the paths in the skill files once:

```powershell
Select-String -Path "skills\*\*.md" -Pattern 'I:/Video Generation/Tools' -List
```

`film.py` itself takes absolute paths on the command line, so the controller works from
anywhere; only the prose in the skills is path-dependent.

## Configuration

### `comfy-film/assets/machine.json`

Created by `install.ps1`, git-ignored, machine-specific.

| Field | Meaning |
|---|---|
| `server` | ComfyUI address the controller queues to. Must match `--port` in `startup.argv`. |
| `python` | The interpreter used for `film.py`. Use ComfyUI's `python_embeded`. |
| `ffmpeg` / `ffprobe` | Absolute paths. A path with spaces is fine. |
| `startup.argv` | Full ComfyUI launch line. Keep `--disable-auto-launch` — without it ComfyUI opens a browser tab on every unattended start. |
| `startup.cwd` | Working directory for the server (the portable ComfyUI folder). |
| `startup.log_dir` | Where server logs are written. |
| `startup.timeout` | Seconds to wait for ComfyUI to answer before `run` gives up. |

Existing projects keep their own copy of these settings inside `film.json`; editing
`machine.json` affects new projects only.

### `comfy-film/assets/youtube.json`

Only needed for publication. Git-ignored: it holds your channel id, playlist ids and
the paths to your OAuth files. Copy `youtube.example.json` and fill it in. Credentials
never belong in a project folder or in this repository.

## What a film looks like

`film init` creates a project folder; everything about the film lives there.

```
<project>/
  film.json                 the record: segments, trims, joins, exports, settings
  brief.md                  creative intent, approved frames, decisions, next action
  frames/                   keyframes (first/last), extracted endpoints
  clips/                    accepted takes, segment-000N.mp4
  .pipeline/                candidates, reviews, guides, logs, workflow-*.json
  outputs/                  stitched assemblies and final exports
```

The chat is not the record. Any chat can be dropped without losing a film — that is
why every decision that matters is written into `film.json` or `brief.md`.

## Workflow in one screen

1. **Plan.** `film init` with canvas and take length, then `film preview` — a sibling
   previz project at 384×672 where the *whole* film is cut to the end and approved as
   one piece. A take there costs ~30 s instead of ~10 min, so a beat the model cannot
   perform is found in minutes.
2. **Boards.** Keyframes are reviewed one at a time. The second keyframe is built by
   editing the first, never generated independently — FL2VA morphs whatever differs
   between them.
3. **Takes.** `film add` → `film run` → `film wait`. Every candidate is measured
   (`motion_profile.py`) and inspected as a 0.5 s contact sheet before it is shown, and
   then shown for an explicit accept/change/reject. Silence is not acceptance.
4. **Continuation.** Every segment after the first is `--guide prev --guide-frames 22
   --last next-board.png`, so the take starts on the previous clip's real pixels. A
   board-to-board cut is where a seam comes from.
5. **Assemble.** `trim` → `join` → `stitch`, with trims on multiples of 1/24 s.
6. **Deliver.** `finalize_delivery.py` → `<name>-final-vN.mp4`, optionally upscaled 2×.
7. **Publish.** Metadata is approved as text before upload; film approval alone never
   authorizes posting.

## Controller cheat sheet

```powershell
$py = 'I:\Video Generation\ComfyUI_windows_portable\python_embeded\python.exe'
$film = 'I:\Video Generation\Tools\comfy-film\scripts\film.py'

& $py $film status  --project PROJECT
& $py $film add     --project PROJECT --first START.png --last END.png --prompt-file PART1.txt --seconds 10
& $py $film run     --project PROJECT
& $py $film wait    --project PROJECT
& $py $film accept  --project PROJECT --segment 1
```

`film init`, `preview`, `add`, `run`, `wait`, `status`, `review`, `accept`, `reject`,
`trim`, `join`, `stitch`, `extract`, `loras`, `recover`, `doctor`, `finalize`.
Every command prints a compact JSON object and fails with a non-zero exit code.

Full syntax: `skills/comfy-film-dsh/references/commands.md`.

## Four modes, one setup

| Mode | What it makes | Controller |
|---|---|---|
| `video` | one clip from a first frame (I2VA) or a first and a last frame (FL2VA) | `film.py` |
| `long` | chained takes: each one starts on the previous clip's pixels | `film.py` |
| `refs` | a character or place taken from 1–9 pictures (Ref2VA) | `film.py` |
| `lipsync` | a character speaks or sings a supplied audio track | `lipsync.py` |

The agent asks this first, because it decides the model download, the prompt shape and what the
reviewer looks at. Details: `skills/comfy-film-dsh/references/modes.md`.

## First run on a machine that has nothing

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File .\setup\install-comfy.ps1 -Modes video,long -Check
```

`-Check` reports the GPU, driver, RAM, free disk, which models are present and which are missing —
and downloads nothing. Drop `-Check` to install: ComfyUI 0.43.0 portable, five node packs pinned to
commits, the model set for the chosen modes, FFmpeg if the machine has none, then
`comfy-film/assets/machine.json`. Downloads resume; existing ComfyUI installs and model files are
detected and left alone.

| Mode group | Download |
|---|---|
| `video` or `long` | ~39 GB |
| `+ refs` | +20 GB (Ref2VA checkpoint) |
| `+ lipsync` | +32 GB (Singularity checkpoint, upscaler) |

Needs an NVIDIA card (RTX 20-series+, 8 GB VRAM), driver 580+, 32 GB RAM and 40–100 GB of disk.
Full detail, flags and troubleshooting: `skills/comfy-film-dsh/references/install.md`.

## Language

Every progress panel and the media watch page are **English by default**. When the agent talks to
the user in Russian, the page follows the conversation:

```powershell
$env:COMFY_FILM_LANG = 'ru'     # one line before `film run`; the panel inherits it
```

Precedence is `--lang` > `COMFY_FILM_LANG` > English. `progress.py`, `upscale_progress.py` and
`image-progress.py` take `--lang ru`; a running panel and the `serve-media.py` watch page switch with
`?lang=ru` / `?lang=en` in the URL. A panel started in one language is restarted by `film run` when
the other one is requested, so the page never contradicts the message next to it.

## The skills

| Skill | Load it when |
|---|---|
| `comfy-film-dsh` | Any film production inside DeepSeek Harness: gates, media links, progress panel, review rules. |
| `comfy-film` | The same work inside Codex. |
| `living-paintings` | A painting video: approach, animation, retreat, and the deterministic compositing that keeps the artwork sharp. |
| `h3-prompt-writing` | Before writing a substantive H3 prompt. Header timecode, shot blocks, soundscape, what the model ignores. |

The skills are the valuable part of this repository. The scripts make the mechanics
possible; the skills are what stop the model from producing a beautiful clip where
nobody moves.

## What is deliberately not committed

| Excluded | Why |
|---|---|
| `deps/`, `youtube-direct/dependencies/` | Vendored Python packages, tens of thousands of files. Install with `pip install --target`. |
| `__pycache__/`, `logs/`, `.pipeline/` | Run artefacts. |
| `agent-model/` | 14.5 GB of llama.cpp and weights, unrelated to the film pipeline. |
| `realesrgan/*.exe`, `realesrgan/models/` | ~100 MB of binaries with their own release page. |
| SeedVR2 weights | Fetched by `seedvr2/download_model.py`. |
| `machine.json`, `youtube.json`, OAuth tokens | Machine- and account-specific. Templates are provided. |
| Project folders (`frames/`, `clips/`, finals) | Yours, not the kit's. |

## Status

- Windows only, by design. The controller is portable Python, but the skills assume PowerShell, junctions and drive letters.
- The Codex skill text (`skills/comfy-film/SKILL.md`) is authored here and installed by `install.ps1 -Force`; the Codex folder itself carries only junctions to `comfy-film/scripts` and `comfy-film/assets`.
- The Codex skill still points at `references/*.md` that live in `skills/comfy-film-dsh/references/`. That inconsistency predates this repository and is a known gap, not a feature.

## License

MIT. See [LICENSE](LICENSE).
