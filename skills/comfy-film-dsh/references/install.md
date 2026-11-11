# Installing the tools

A machine that has never generated a film needs ComfyUI, five node packs, a model set per mode and
FFmpeg. `setup/install-comfy.ps1` installs all of it, resumes broken downloads and skips everything
that is already there.

## 1. Check first — never download blind

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File `
  '$Tools\setup\install-comfy.ps1' -Modes video,long -Check
```

Read the last line — it starts with `##RESULT##` and is a compact JSON object:

| Field | Meaning |
|---|---|
| `status` | `ready` (nothing to do), `missing` (something is absent), `installed`, `error` |
| `comfy_present` | ComfyUI's embedded Python exists |
| `missing` | model file names still to download |
| `gpu`, `vram_gb`, `driver`, `ram_gb`, `disk_free_gb` | what the machine is |
| `profile` | `lite` / `standard` / `max` — which checkpoint size the plan picked |
| `errors` | reasons, when `status` is `error` |

Stop here and tell the user what is missing **before** downloading anything. If `status` is `ready`,
skip to step 4.

## 2. Ask before installing

One message, then one question:

- **Which modes?** They come from `modes.md`. The download is per mode group: `video`/`long` 39 GB,
  `refs` +20 GB, `lipsync` +32 GB (a different checkpoint). Modes share the encoder and VAEs.
  Only what the chosen modes need is installed: the model roles **and** the node packs (for example
  `video` pulls one pack, `lipsync` three). `-Check` prints both lists before anything is downloaded.
  `-Modes` is required — with no modes the script stops and lists the options instead of guessing.
- **Where?** The default is an existing ComfyUI, otherwise the fixed drive with the most free space.
  Say the path you are about to use. If neither exists, nothing is guessed: `install.ps1` reports
  "ComfyUI was not found" and leaves `machine.json` alone, and the engine installer reports the path
  it *would* use — then the choice is the user's, passed as `-ComfyRoot`.
- **Time.** Tens of GB over a home connection is hours. Downloads resume, so an interrupted run is
  not a restart — rerun the same command.

Do not start an install the user did not approve, even when `-Check` proves it is needed.

## 3. Install

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File `
  '$Tools\setup\install-comfy.ps1' -Modes video,long,refs,lipsync
```

Run it as a background job and collect it with `job_output` — it prints a line per file with GB and
percent, so the user can watch progress in the tool output. Options:

| Flag | Use it when |
|---|---|
| `-ComfyRoot <path>` | the install must go somewhere specific |
| `-Profile lite\|standard\|max` | the GPU is small (`lite`) or huge (`max`); `auto` decides by VRAM + RAM |
| `-VideoModel nvfp4` | RTX 50-series with 16 GB+ (auto-selects it) |
| `-SkipNodes` / `-SkipFFmpeg` | those parts already exist elsewhere |
| `-Force` | rewrite `machine.json` |
| `-Retries N` | a flaky connection (default 20 attempts per file) |

What it writes: `<ComfyUI>\models\<category>\<file>`, `comfy-film/assets/machine.json` with the
embedded Python, the FFmpeg pair and the ComfyUI startup line.

## 4. Verify

```powershell
$py = '$Comfy\python_embeded\python.exe'
& $py '$Tools\comfy-film\scripts\film.py' doctor --project <an existing project>
& $py '$Tools\comfy-film\scripts\film.py' start  --project <an existing project>
```

`doctor` checks node classes, FFmpeg and the optional libraries without loading models. `start`
launches ComfyUI; a server that answers `/system_stats` means the install is usable.

## Requirements and refusals

- **NVIDIA, RTX 20-series or newer, 8 GB VRAM minimum** (16 GB is the comfortable floor). The
  bundled PyTorch is CUDA 13 — **driver 580 or newer**, or ComfyUI will not start.
- 32 GB RAM recommended; ComfyUI keeps what does not fit in VRAM in system RAM.
- 40–100 GB of disk depending on modes. The installer warns when free space is below the plan.
- Windows 10/11. `curl.exe` ships with Windows 10 1803+ and is the downloader; without it the script
  fails early with a clear message.

The script installs anyway when there is no NVIDIA card — it just says so. ComfyUI on CPU is not a
film pipeline; treat that as "this machine cannot generate".

## What gets installed

| Part | Source | Size |
|---|---|---|
| ComfyUI 0.43.0 portable (NVIDIA build) | `Comfy-Org/ComfyUI` release | ~2 GB |
| Node packs | `ComfyUI-H3-NativeAudioLock`, `Comfyui_Minimax_h3_latent_Upscaler`, `ComfyUI-MelBandRoFormer`, `ComfyUI-VideoHelperSuite`, `ComfyUI-KJNodes` — pinned commits, no git needed | tens of MB |
| Models | `Comfy-Org/MiniMax-H3`, `WarmBloodAban/Minimax-h3_Singularity`, `LBH-123-AI`, `Kijai` | 39–90 GB |
| FFmpeg | gyan.dev essentials build, only if none is found | ~80 MB |

The catalog with URLs, sizes and mode→role mapping is `setup/catalog.json`, generated from the
Minimax H3 Workspace catalog. Edit that file, not the script, when a model moves.

## Existing installs

- An existing ComfyUI is detected by `<ComfyRoot>\python_embeded\python.exe` and left alone.
- A model already on disk counts as present whether it sits in the category root or in a subfolder
  (`diffusion_models\MinimaxH3\...`); nothing is downloaded twice. The controller itself addresses
  models by bare filename, so a fresh install puts them in the category root.
- `machine.json` is not overwritten without `-Force`.

## Troubleshooting

| Symptom | What it means |
|---|---|
| `HTTP 403` from huggingface.co | rate limit or a gated repo; wait and rerun — the `.part` file resumes |
| ComfyUI starts and exits at once | driver older than 580, or VRAM too small for the selected profile |
| `ComfyUI has no MiniMaxH3NativeAudioLock` from `lipsync.py` | node packs were skipped; run the installer without `-SkipNodes` |
| `Cannot list X from ComfyUI` | the node exists but its inputs differ — check the node pack version |
| Download stalls at the same percent | a proxy/VPN; the script retries 20 times, then fails with curl's message |
