# New-project setup

**Step 0 — is the machine able to run the chosen mode?** Run the installer check from
`install.md` before promising anything: `setup/install-comfy.ps1 -Modes <mode> -Check`. If it reports
`missing`, that is a conversation (modes, disk, time), not something to improvise around.

Ask only for missing choices, before creating assets or queueing generation. Do not repeat saved settings when continuing. Use the user-input tool when available, otherwise a compact numbered menu. Ask at most three questions in a batch; the user may answer in free text. Put a recommended choice first, based on the stated use case. User-specified values and delegated choices override these suggestions.

First batch (Russian examples; adapt to the user's language):

1. **Режим?** Короткое видео: один кадр или первый и последний; длинное видео из сцен, где каждая продолжает предыдущую; референсы (персонаж и место по картинкам); lipsync под ваше аудио. Recommend by intent: one shot or a pinned transition → `video`; a story longer than 15 seconds or a loop → `long`; a character that must not change between shots → `refs`; speech or a song → `lipsync`. Full comparison, prompts and flags: [modes.md](modes.md). Ask this one **first** — it decides the model download, the prompt shape and the review question.
2. **Формат видео?** Вертикальный 9:16 (Shorts/Reels); горизонтальный 16:9 (обычный фильм); квадратный 1:1. Recommend according to the user's intended platform, not always portrait. Support custom proportions/resolution in free text.
3. **Профиль генерации?** Быстрый тест — базовое разрешение, Turbo 8; больше деталей — повышенное разрешение, Turbo 8; обычный режим — повышенное разрешение, 20 шагов без Turbo. Recommend a quick test first if settings are untested. Higher resolution/steps take longer and may not produce a better shot; do not label standard as guaranteed best.
4. **Длительность каждой части?** 10 секунд (recommended starting point); 15 секунд. Explicitly tell the user they can enter a custom duration from 4 to 15 seconds, including fractional values such as 7.5 or 12. Do not treat the suggested options as an exhaustive list. Mention rounding only briefly when relevant. Total film length is independent of this choice.

Ask questions 1–4 in one batch of at most three cards only when the mode is already known; with an
unknown mode, ask the mode alone first, then the rest.

Canvas/profile mapping (all dimensions divisible by 32):

| Format | Base | Higher detail |
|---|---|---|
| Portrait | 608×1056 | 864×1536 |
| Landscape | 1056×608 | 1536×864 |
| Square | 768×768 | 1152×1152 |

Base rectangular ratios are approximate due to the model's dimension grid. If exact 9:16 / 16:9 matters, choose 576×1024 / 1024×576 or the higher-detail canvas. Do not force a claimed exact ratio by stretching.

Second batch, only as needed:

- **Звук?** Звуки сцены, музыку добавим позже (recommended); звуки и музыка при генерации; без звука. Map to --audio generated/--music later; generated/generated; silent/none. Silent export does not mean H3 skips joint audio latent computation.
- **Сюжет и объём?** If not already known, ask what should happen and the intended total length (e.g. 20–30 seconds, about a minute, or open-ended with review of each part). Do not invent a fixed number of clips if the user has not chosen it. For a longer film, draft a small shot plan in brief.md.
- **Нужна петля?** Зацикленный ролик; обычное начало и завершение. Recommend based on the concept. For a loop the final segment ends on the extracted first frame (`film extract --segment 1 --which first --scale 1`) passed as `--last` — `--loop` cannot be combined with `--guide`, and every segment after the first is a guide continuation. Other films do not automatically dissolve back to their first frame.

Infer an English project name/path from the title and established destination convention. Ask about destination only if genuinely ambiguous; do not burden the user with routine file naming. Keep 24 fps for this H3 workflow rather than offering unsupported frame rates.

After the answers, give a one-line recap and create the project. Do not add another approval round for settings already selected. Example:

```powershell
film init --project PROJECT --width 864 --height 1536 --quality turbo --seconds 10 --audio generated --music later
```

Create the preview sibling in the same step, always — pass 1 of every film happens there:

```powershell
film preview --project PROJECT          # '<project> previz 384x672', 5 s takes, ~30 s each
```

The whole film is cut to the end at 384×672 and approved as one film; only then is the same
segmentation re-shot at native size in the film's own project. Boards and prompt files are shared
between the two projects. Say this once when the project is created, so the user knows which render is
which and why the native takes come later.

Quality flags: turbo toggles the bundled turbo switch on (8 steps); standard turns it off (20 steps). Custom workflows without that switch can use --quality workflow and their own validated settings. Initial choices persist for future parts; add inherits --seconds unless overridden explicitly.

Use saved audio/music settings when writing prompts: non_diegetic_music is N/A for none/later, a musical description for generated. With silent audio, describe no sound and do not promise a generated soundtrack. The controller's --music stores the choice; prompt content determines generated music.

If the user says “на твой выбор” or “как обычно”, use existing series preferences where available. Otherwise choose a small Turbo test, 10 seconds and scene sounds with music later; infer format from platform. State these assumptions once. Do not ask the full questionnaire again after every accepted clip.
