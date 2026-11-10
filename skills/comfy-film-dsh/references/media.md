# Showing media to the user in DSH

Three hard facts about this GUI, learned the slow way:

- chat images and file cards do not render for this user;
- the sidebar opens **images and documents** from a local path, but **cannot preview video** — an `.mp4` opens only over HTTP;
- OS windows are unwanted: `Start-Process` on a media path triggers the stale Windows association dialog.

So the rule is split by type.

## Images and documents — path link

```markdown
[keyframes-compare.png](<I:\Video Generation\Elemental Creatures\moss snail\.pipeline\keyframes-compare.png>)
[prompt-ru-part1-v3.txt](<I:\Video Generation\Elemental Creatures\moss snail\prompt-ru-part1-v3.txt>)
```

Absolute path, angle brackets (spaces), link in normal text — not inside a code block.

## Video — HTTP link from the preview server

Start the server once per session; it serves the whole tree, so every project shares it.

```powershell
$py = 'C:/Users/avaln/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
& $py 'I:\Video Generation\Tools\skills\comfy-film-dsh\scripts\serve-media.py' `
    --directory 'I:/Video Generation' --port 8199                        # background job
```

Use `serve-media.py`, not `python -m http.server`. The stdlib handler ignores the
`Range` header, so it replies `200` with the entire file; the player cannot seek,
aborts on the first scrub, and floods stderr with `ConnectionResetError`
tracebacks. `serve-media.py` answers `206` with `Content-Range`, supports `HEAD`,
and treats a dropped client as normal.

### Always link `/watch/`, never the file path

DSH's embedded Browser shows a red banner — «The page could not load; reload or
open it in the system browser.» — when a navigation targets a media file
directly. Chromium cancels the document load and commits a media viewer instead,
which DSH reports as `did-fail-load`; the retry then succeeds, so the banner
appears once per tab and looks like a broken server. `/watch/<path>` returns a
tiny HTML page with a `<video>` element, which commits normally, so the banner
is gone. The raw path still works and still supports `Range`; use it only inside
the page, or for `curl`/ffmpeg checks.

Then post the URL, relative to `I:/Video Generation` and URL-encoded:

```
http://127.0.0.1:8199/watch/Elemental%20Creatures/moss%20snail/outputs/moss-snail-final-v15.mp4
```

Verify before posting — a dead link is worse than no link:

```powershell
(Invoke-WebRequest -Uri <url> -Method Head).StatusCode          # expect 200
(Invoke-WebRequest -Uri <url> -Headers @{Range='bytes=0-1023'}).StatusCode   # expect 206
```

The server's stdout must stay one line per request. Tracebacks there mean real
breakage, not scrubbing; a healthy stream of `206`s with no stderr is the goal.

## Review sequence

1. Copy the candidate to a stable path inside the project, e.g. `outputs/review-part-N.mp4`.
2. Video: post the `http://127.0.0.1:8199/watch/...` link as the first thing the user reads.
3. Stills: post the path link; when comparing two frames, compose a labelled side-by-side PNG with PIL first and link that one file.
4. Say in the same message what you see and what the decision hinges on — the observed defect, the measured numbers, the trade-off.
5. **Then** call `ask_user_question` with a one-line question and bare option labels (Принимаем / Нужно изменить / Отклоняем).

**Tests and preview takes count too.** Every render that reaches the disk gets a link, in a list with one
line each — a failed variant, a camera-drift test, a 30 s previz take, an A/B pair. Never summarise a
batch of test renders without showing them: the numbers are an argument, the clips are the evidence, and
the user is the one judging. Name the stable copies by what they test (`s1-v3-komanda-stuk.mp4`), so the
list stays readable after the chat is gone.

**One take per message.** Post the link as soon as the render lands and end the turn there; do not start
the next take before it has been seen. Cheap previews are not an exception — the point of showing each
fragment is that the user catches a wrong beat before it is built into the chain. Batch six takes into one
message and the only thing left to do is re-shoot them all.

Links and findings belong to steps 2–4, in the chat message. The question card is only the choice: text pushed into the question field or into option descriptions replaces the preview the user needs to read, and they will say so. Same rule for publication: the full title and description go in the message as a text block, the card asks only "Публикуем?".

## Never

- `Start-Process` on a media path — stale associations (`.mp4` bound to a UWP app by hashed ProgId, `.png` to WPS Office) produce a "How do you want to open this file?" dialog.
- The `open-media.ps1` helper as a default — it opens Edge outside the sidebar. Fallback only.
- A path link for `.mp4` and an HTTP link for `.png` — that is exactly backwards.
- Links or long payloads inside `ask_user_question` — they belong in the message before it (non-negotiable 9 in SKILL.md).

Stop the preview server when the work is parked or the film is published.
