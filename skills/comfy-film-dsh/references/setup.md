# New-project setup

**Step 0 — is the machine able to run the chosen mode?** Run the installer check from
`install.md` before promising anything: `setup/install-comfy.ps1 -Modes <mode> -Check`. If it reports
`missing`, that is a conversation (modes, disk, time), not something to improvise around.

Ask only for missing choices, before creating assets or queueing generation. Do not repeat saved settings when continuing. Use the user-input tool when available, otherwise a compact numbered menu. Ask at most three questions in a batch; the user may answer in free text. Put a recommended choice first, based on the stated use case. User-specified values and delegated choices override these suggestions.

First batch (Russian examples; adapt to the user's language):

1. **Режим?** Короткое видео: один кадр или первый и последний; длинное видео из сцен, где каждая продолжает предыдущую; референсы (персонаж и место по картинкам); lipsync под ваше аудио. Recommend by intent: one shot or a pinned transition → `video`; a story longer than 15 seconds or a loop → `long`; a character that must not change between shots → `refs`; speech or a song → `lipsync`. Full comparison, prompts and flags: [modes.md](modes.md). Ask this one **first** — it decides the model download, the prompt shape and the review question.
2. **Формат?** Шесть соотношений, как в настройках режима у H3 Workspace: вертикальное 9:16 (Shorts/Reels); горизонтальное 16:9 (обычный фильм); квадрат 1:1; 4:3; 3:4; кино 21:9. Recommend by platform and subject, not always portrait.
3. **Размер?** Четыре ступени площади кадра: 0.3 МП — быстрый тест; 0.64 МП — базовый (рекомендуется для первой серии); 1.06 МП — HD+; 1.87 МП — крупный. Любое другое число мегапикселей принимается словами («около 1.5»). Resolution and step count are separate questions — do not bundle them.
4. **Шаги?** `turbo` — 8 шагов, обычное качество; `fast` — 4 шага с Turbo-SLA, вдвое быстрее и мягче (черновик); `standard` — 20 шагов без Turbo, самый медленный; `draft` — 4 шага DMAD для черновой раскадровки. Recommend turbo for a first film and fast for previz.

5. **Длительность каждой части?** 10 секунд (recommended starting point); 15 секунд. Explicitly tell the user they can enter a custom duration from 4 to 15 seconds, including fractional values such as 7.5 or 12. Do not treat the suggested options as an exhaustive list. Total film length is independent of this choice.

Ask the mode alone first when it is unknown; then format + size + steps in one card of three; then
duration and sound in the next, with plot and loop only if the concept needs them.

Canvas: `film init --aspect 9:16 --megapixels 0.64` computes the pair and snaps both sides to 32 px —
the same arithmetic as the app. The full grid, so the recommendation is concrete:

| Aspect | 0.3 | 0.64 | HD+ | 1.87 |
|---|---|---|---|---|
| 16:9 | 736×416 | 1056×608 | 1376×768 | 1824×1024 |
| 9:16 | 416×736 | 608×1056 | 768×1376 | 1024×1824 |
| 1:1 | 544×544 | 800×800 | 1024×1024 | 1376×1376 |
| 4:3 | 640×480 | 928×704 | 1184×896 | 1568×1184 |
| 3:4 | 480×640 | 704×928 | 896×1184 | 1184×1568 |
| 21:9 | 832×352 | 1216×512 | 1568×672 | 2080×896 |

Exact ratios are impossible on the 32-pixel grid, so state the resulting canvas rather than a promise
of «ровно 9:16». Never stretch a frame to fake a ratio.

Second batch, only as needed:

- **Звук?** Звуки сцены, музыку добавим позже (recommended); звуки и музыка при генерации; без звука. Map to --audio generated/--music later; generated/generated; silent/none. Silent export does not mean H3 skips joint audio latent computation.
- **Сюжет и объём?** If not already known, ask what should happen and the intended total length (e.g. 20–30 seconds, about a minute, or open-ended with review of each part). Do not invent a fixed number of clips if the user has not chosen it. For a longer film, draft a small shot plan in brief.md.
- **Нужна петля?** Зацикленный ролик; обычное начало и завершение. Recommend based on the concept. For a loop the final segment ends on the extracted first frame (`film extract --segment 1 --which first --scale 1`) passed as `--last` — `--loop` cannot be combined with `--guide`, and every segment after the first is a guide continuation. Other films do not automatically dissolve back to their first frame.

Infer an English project name/path from the title and established destination convention. Ask about destination only if genuinely ambiguous; do not burden the user with routine file naming. Keep 24 fps for this H3 workflow rather than offering unsupported frame rates.

After the answers, give a one-line recap and create the project. Do not add another approval round for settings already selected. Example:

```powershell
film init --project PROJECT --aspect 9:16 --megapixels 0.64 --quality turbo --seconds 10 --audio generated --music later
```

Create the preview sibling in the same step, always — pass 1 of every film happens there:

```powershell
film preview --project PROJECT          # '<project> previz 384x672', 5 s takes, ~30 s each
```

The whole film is cut to the end at 384×672 and approved as one film; only then is the same
segmentation re-shot at native size in the film's own project. Boards and prompt files are shared
between the two projects. Say this once when the project is created, so the user knows which render is
which and why the native takes come later.

Quality flags: turbo toggles the bundled turbo switch on (8 steps); fast uses the Turbo-SLA LoRA at 4 steps with shifts 6/3; standard turns turbo off (20 steps); draft uses the DMAD LoRA with the lcm sampler. Custom workflows without that switch can use --quality workflow and their own validated settings. Initial choices persist for future parts; add inherits --seconds unless overridden explicitly.

Use saved audio/music settings when writing prompts: non_diegetic_music is N/A for none/later, a musical description for generated. With silent audio, describe no sound and do not promise a generated soundtrack. The controller's --music stores the choice; prompt content determines generated music.

If the user says “на твой выбор” or “как обычно”, use existing series preferences where available. Otherwise choose a small Turbo test, 10 seconds and scene sounds with music later; infer format from platform. State these assumptions once. Do not ask the full questionnaire again after every accepted clip.
