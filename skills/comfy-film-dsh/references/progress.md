# Progress panel in DSH

`film run` starts a helper and returns its URL in the `progress` field. **That URL is not
durable in DSH**: the helper is a child of the `run` process, and when `run` returns the
command's job object closes and the helper exits. The port is dead by the time the user
clicks it.

Start the panel yourself, once per project, as a persistent background job:

```powershell
$py = 'C:/Users/avaln/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
& $py 'I:/Video Generation/Tools/comfy-film/scripts/progress.py' `
    --project 'I:/Video Generation/Elemental Creatures/<name>' --serve      # run_in_background
```

`--serve` writes `.pipeline/progress-server.json` (`url`, `pid`) and keeps serving. Verify
before posting, every time:

```powershell
$r = Get-Content '<project>\.pipeline\progress-server.json' | ConvertFrom-Json
(Invoke-WebRequest "$($r.url)/api" -TimeoutSec 5).Content     # must return the project JSON
```

`/api` returning the film's title and the running segment means the panel is alive. A refused
connection means it was launched without `--serve`, or the launching command has ended —
relaunch as a background job and post the **new** URL.

Rules:

- Post the verified URL in the **same message as the run submission**, before starting the `wait`
  background job. Not after the render, not only in the tool JSON. This is the one thing the user
  watches while a take runs.
- Post the verified URL in the same message as the run/wait update. Never post an unchecked link.
- One panel per project; do not start a second one while `/health` answers.
- The percentage describes sampling steps, never total render time.
- The panel is a convenience, not a gate: if it refuses to start, continue the render and say the
  panel is down. Do not debug browser access.
- DSH has no embedded browser. The user opens the URL; there is nothing to automate here.
- When the film is published or the work is parked: kill the background job and the `pid` from
  `.pipeline/progress-server.json`.

Manual one-shot start (no `--serve`) is only for a quick look from a terminal that stays open.

## Language

The panel is **English by default**. When the conversation with the user is Russian, the panel is
Russian too:

```powershell
$env:COMFY_FILM_LANG = 'ru'     # one line before `film run`; the panel inherits it
& $py 'I:/Video Generation/Tools/comfy-film/scripts/progress.py' `
    --project 'I:/Video Generation/Elemental Creatures/<name>' --serve --lang ru
```

Precedence: `--lang` > `COMFY_FILM_LANG` > English. A running panel keeps the language it was
started with — `film run` restarts a panel whose language differs, so the page always matches the
chat. Append `?lang=ru` or `?lang=en` to a panel URL to switch one view without restarting it. The
same rule applies to `upscale_progress.py`, `image-progress.py` and the `serve-media.py` watch page.

Never mix: a Russian message with an English panel reads as a bug, and vice versa.
