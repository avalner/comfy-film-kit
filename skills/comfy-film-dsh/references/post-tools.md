# Post-production tools in ComfyUI

Installed 2026-10-29 into `I:\Video Generation\ComfyUI_windows_portable\ComfyUI\custom_nodes`:

| Pack | Repo | Nodes we use |
|---|---|---|
| ProPainter | [daniabib/ComfyUI_ProPainter_Nodes](https://github.com/daniabib/ComfyUI_ProPainter_Nodes) | `ProPainterInpaint`, `ProPainterOutpaint` |
| Frame Interpolation | [Fannovel16/ComfyUI-Frame-Interpolation](https://github.com/Fannovel16/ComfyUI-Frame-Interpolation) | `RIFE VFI`, `FILM VFI`, others |
| VideoHelperSuite | [Kosinkadink/ComfyUI-VideoHelperSuite](https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite) | `VHS_LoadVideoPath`, `VHS_LoadImagesPath`, `VHS_VideoCombine` |

`opencv-contrib-python` and `imageio-ffmpeg` were added to the ComfyUI embedded Python for these packs.
The `deps\` folder of the film pipeline also contains opencv for `film.py`; that is separate and stays.

## After installing or updating a pack

ComfyUI only registers nodes at startup. Restart it and verify:

```powershell
$p = Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -like '*ComfyUI*main.py*' }
if ($p) { Stop-Process -Id $p.ProcessId -Force }
& 'I:\Video Generation\ComfyUI_windows_portable\python_embeded\python.exe' 'I:\Video Generation\Tools\comfy-film\scripts\film.py' start --project 'I:/Video Generation/Elemental Creatures/<name>'
```

Then check `http://127.0.0.1:8188/object_info` for `ProPainterInpaint`, `RIFE VFI`, `VHS_LoadVideoPath`.
A missing node pack usually means a Python import error at startup — read the newest `logs\comfyui-*.log` in the pipeline folder.

## RIFE: smooth speed change

Why: the plain ffmpeg speed-up (`setpts=PTS/1.3` + `fps=24`) duplicates frames, which shows as slight stepping on fast motion. Interpolating to 48 fps first gives the 1.3× sampler real frames to draw from.

Numbers: a 24 fps source played at 1.3× needs 31.2 fps of content. A 48 fps interpolated source provides 48 / 1.3 ≈ 36.9 fps after the speed-up, so the 24 fps result is built from true intermediate frames.

Tested workflow: `assets/workflows/rife-2x.json` (485 frames out of a 243-frame 10 s clip, audio preserved, ~40 s on this GPU).

One command does the whole chain:

```powershell
& $emb 'I:\Video Generation\Tools\skills\comfy-film-dsh\scripts\rife.py' `
  --input 'I:\...\clips\segment-0015.mp4' --speed 1.3 --prefix 'rife_test/name' --out 'I:\...\out.mp4'
```

It interpolates, then retimes with `setpts` + `atempo`, prints the interpolated path, the output probe and the final path. Tested on a 10.125 s clip: 485 frames at 48 fps, then 187 frames at 24 fps / 7.79 s.

Manual route, if the script is unavailable:

1. Replace `VIDEO_PATH` and `filename_prefix`, POST the JSON to `/prompt` with `{"prompt": <graph>, "client_id": "..."}`.
2. Poll `/history/<prompt_id>`; the result is `ComfyUI/output/<prefix>_00001-audio.mp4` at 48 fps.
3. Speed it up and deliver:

```powershell
$ff = 'C:/Program Files/Shotcut/ffmpeg.exe'
& $ff -y -i IN_48FPS.mp4 -filter_complex "[0:v]setpts=PTS/1.3,fps=24[v];[0:a]atempo=1.3[a]" `
  -map "[v]" -map "[a]" -c:v libx264 -crf 17 -preset fast -pix_fmt yuv420p `
  -c:a aac -b:a 192k -movflags +faststart OUT_24FPS.mp4
```

Notes:
- `VHS_LoadVideoPath` outputs are `IMAGE, frame_count, audio, video_info` — audio is output index **2**. Linking index 1 fails validation with a type mismatch.
- `format: "None"` on the loader avoids AnimateDiff-style frame packing.
- `multiplier: 2` doubles the frame count; `multiplier: 4` at 96 fps is only worth it for real slow motion.
- First run downloads the RIFE weights (`rife49.pth`) next to the node.
- For slow motion instead of speed-up, interpolate and keep the original frame rate, then `setpts=PTS*2`.

Honest measurement on a slow, static-camera clip (moss snail part 1): old duplicate method vs RIFE, 187 frames each — mean frame-to-frame difference 0.67 vs 0.66, 95th percentile 1.31 vs 1.06. The gain is small when the subject barely moves. Expect the real benefit on fast motion (wings, running, shaking), where `fps=24` after `setpts` visibly steps. Do not spend RIFE time on near-static shots.

## ProPainter: remove an object the generation refused to lose

Use when a take is otherwise good but carries a stuck artifact: beads on a shell, a crumb that will not disappear, an extra object, a moss patch that pops.

Chain:

```
VHS_LoadVideoPath (video)
VHS_LoadVideoPath (mask video, format "None")  -> ImageToMask (channel red)
ImageToMask -> ProPainterInpaint.mask
VHS_LoadVideoPath (video) -> ProPainterInpaint.image
ProPainterInpaint -> VHS_VideoCombine
```

Mask: white where the object is, black elsewhere, same resolution as the video, one mask frame per video frame (or a single repeated frame for a static camera). Build it with ffmpeg so it stays deterministic:

```powershell
# static box mask over the artifact, 608x1056, h264 so VHS can load it
& $ff -y -f lavfi -i color=c=black:s=608x1056:r=24 -t 10.125 `
  -vf "drawbox=x=250:y=620:w=140:h=120:color=white:t=fill" `
  -c:v libx264 -pix_fmt yuv420p mask.mp4
```

`ProPainterInpaint` parameters that matter:

| Parameter | Default | Meaning |
|---|---|---|
| `mask_dilates` | 5 | grow the mask before inpainting; raise to 8–12 when the object has a soft edge or a shadow |
| `ref_stride` | 10 | how far it looks for clean reference frames; lower for fast-moving backgrounds |
| `neighbor_length` | 10 | temporal window for propagation |
| `subvideo_length` | 80 | frames per chunk; lower it if VRAM runs out |
| `raft_iter` | 20 | flow precision; 10–12 is usually enough |
| `fp16` | enable | keep on unless artifacts appear |

Expect the object's area to be rebuilt from surrounding frames, so it works best on textured backgrounds (moss, bark, water) and worst on flat gradients with moving highlights. Verify by extracting before/after frames of the same timestamp and comparing.

Caveats:
- First run downloads ProPainter weights (a few hundred MB) into the node's `weights` folder.
- A 243-frame 608×1056 clip fits comfortably; long clips should be processed in chunks.
- `ProPainterOutpaint` exists but the paper authors warn its quality is lower; treat it as experimental.

## When not to use these

- Structural story fixes (a missing beat, wrong timing, wrong pose) — that is a regeneration, not post.
- Eye or face deformation from fast motion — usually cheaper to cut or slow that window than to inpaint.
- Anything where the model already delivered a clean take: post costs GPU time and can introduce its own artifacts.
