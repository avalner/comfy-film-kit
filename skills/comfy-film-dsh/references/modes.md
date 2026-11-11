# Modes

Ask which mode this film is **before** designing keyframes or drafting a prompt. The modes are not
interchangeable: each has its own model set, its own prompt shape and its own review question.

| Mode | What the user gets | Controller | Install (`setup/install-comfy.ps1`) |
|---|---|---|---|
| `video` | One clip, 4–15 s, from one keyframe (I2VA) or two (FL2VA) | `film.py` | `-Modes video` — 39 GB |
| `long` | A film of chained takes: every take starts on the previous clip's pixels | `film.py` | `-Modes long` — the same files as `video` |
| `refs` | A character, place or object taken from 1–9 pictures (Ref2VA) | `film.py` | `-Modes refs` — 39 GB |
| `lipsync` | A character speaks or sings a supplied audio track | `lipsync.py` | `-Modes lipsync` — 52 GB |

The numbers are the model download for that mode alone; modes share the encoder and the VAEs, so
`video,long` together is still ~39 GB, and adding `refs` adds one 20 GB checkpoint.

## How to ask

One question, mode first, then only the details that mode needs:

- **video** — portrait or landscape, how long, sound with the picture or music later?
- **long** — how many scenes, total length, must it loop back to the first frame?
- **refs** — which pictures are the anchors (character / place / prop), and is identity or setting
  the thing that must not drift?
- **lipsync** — the audio file, 1–9 reference pictures, and what the character is doing while
  speaking.

If the user says "как обычно" or "на твой выбор", take the series default (portrait 768×1344,
10 s for `video`, 5–6 s takes for `long`, sound from the model, music later) and state it once.

**Mode is a project decision, not a per-segment one.** A project is one mode; two modes are two
projects. The exception is `refs`, which combines with the others: a Ref2VA take can also carry
`--first`, `--last` and `--guide` (the references describe *who*, the keyframes fix *where*).

---

## video — one clip, one shot

```powershell
film add --project PROJECT --first frame.png --last end.png --prompt-file part-1.txt --seconds 10
film add --project PROJECT --first frame.png --prompt-file part-1.txt --seconds 10      # I2VA
```

- I2VA (only `--first`) drifts: the model invents where the shot goes. Use it when the frame already
  contains the action's starting pose.
- FL2VA (`--first` + `--last`) pins both ends and decelerates into the last frame — see
  non-negotiable 8: do not end on the apex of a movement.
- The duration is 4–15 s; H3 rounds to its 17k+5 grid (10 s → 243 frames). Longer stories are
  `long`, not a longer take.

## long — chained takes

Every take after the first is generated from the previous clip's actual pixels, never from a second
board:

```powershell
film add --project PROJECT --guide prev --guide-frames 22 --last board-2.png --prompt-file part-2.txt --seconds 6
```

- 22 guide frames (0.92 s); the first *shown* frame is frame 22.
- 5–6 s per take. Past ~6.6 s the camera and the character drift.
- The last keyframe is a settled pose; without it the chain invents its own ending.
- Build the whole film at 384×672 first (`film preview`), approve the cut, then re-shoot at native.
  This is non-negotiable 12 and it is exactly where a `long` film burns its money.

## refs — references (Ref2VA)

```powershell
film add --project PROJECT --ref2va hero.png --ref2va room.png `
    --ref2va-model minimax_h3_ref2va_pruned_int8_convrot.safetensors `
    --ref2va-lora minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors `
    --ref2va-steps 6 --ref2va-size match `
    --first board-1.png --prompt-file part-1.txt --seconds 8
```

- 1–9 pictures. The prompt must name them: `<Picture 1>` is the hero, `<Picture 2>` the room.
- `--ref2va-model` switches the diffusion model for this take; without it the project's FL2VA model
  is used, which is not trained for reference conditioning. Full model names are what
  `film loras`-style resolution expects: a bare filename, as ComfyUI lists it.
- `--ref2va-lora` + `--ref2va-steps 4–8` is the fast path (turbo), 20–25 steps without it.
- `--ref2va-size max` keeps more reference detail and is several times slower; `match` fits the
  references to the canvas and is the default.
- Because the model changes, judge the take against the references first (identity, costume, place)
  and only then against the keyframe composition.

`mode` in the `add` output reads `ref2va+i2va`, `ref2va+fl2va` or `ref2va+guide+last` — that string
tells you which anchors are actually in the graph.

## lipsync — the character speaks your audio

```powershell
$py 'I:\Video Generation\Tools\comfy-film\scripts\lipsync.py' `
    --audio voice.mp3 --ref face.png --ref face-side.png `
    --prompt-file lipsync.txt --project 'I:\Video Generation\Projects\<film>'
```

- The video follows the audio: length comes from the file, not from `--seconds` (`--seconds` only
  cuts it shorter).
- 1–9 reference pictures; faces work best cropped close, one frontal and one three-quarter.
- The prompt is wrapped into H3's structured form automatically unless it already contains
  `integrated_multimodal_description`. Write the action ("She looks into the lens, eyebrows lift,
  then a small nod"), not the words — the words are in the audio.
- Two passes: 12 steps, split at 8; the second half finishes a latent upscaled by `--scale`
  (default 2.0). `--scale 1.5` is cheaper; below 1.5 the face softens.
- Output: `clips/lipsync-000N.mp4` in the project, plus a journal record in `.pipeline/lipsync/`
  with the seed, models and source audio.
- Model names are resolved from ComfyUI's own lists, so an existing checkpoint in a subfolder is
  used instead of downloading a second copy. Override with `--unet`, `--lora`, `--clip`,
  `--video-vae`, `--audio-vae`, `--upscaler`.
- Lipsync is a **single take**. Do not try to chain two lipsync clips with `--guide`: the audio
  lock is per take and the second take would restart the sound.

## Review gates are the same in every mode

An accepted take, a rejected take, a measured take — the rules in `SKILL.md` do not change with the
mode. What changes is what you look at:

| Mode | Judge first |
|---|---|
| `video` | did the beat happen, or did the subject stand still |
| `long` | the join: last frame of take N against frame 22 of take N+1 |
| `refs` | identity and costume against the reference pictures |
| `lipsync` | mouth sync and the face at 1:1, then the audio cut |
