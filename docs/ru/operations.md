# Эксплуатация комплекта

Заметки для этой машины. Канонический путь — `I:\Video Generation\Tools\`; если папка
лежит в другом месте, замените префикс, остальное не меняется.

## Раскладка

```
I:\Video Generation\Tools\
  comfy-film\scripts\      film.py, finalize.py, progress.py, youtube*.py, match_lighting.py, film.cmd
  comfy-film\assets\       machine.json (путь к Python, запуск ComfyUI), workflow-api.json (шаблон графа)
  comfy-film\tests\        test_pipeline.py — 10 автотестов на фейковом API, GPU не нужен
  comfy-film\deps\         локальные пакеты вне окружения ComfyUI (opencv-headless)
  comfy-film\logs\         comfyui-*.log из автозапуска сервера
  skills\                  comfy-film-dsh, comfy-film, living-paintings, h3-prompt-writing
  seedvr2\                 апскейл SeedVR2 3B FP16 для финальной выдачи
  realesrgan\              опциональный ncnn-апскейл (бинарники не в репозитории)
```

`deps\`, `logs\`, `deps`-пакеты YouTube и `agent-model\` в git не попадают — см. `.gitignore`.

## Интерпретатор

Всё считается встроенным Python из ComfyUI:

```powershell
$py = 'I:\Video Generation\ComfyUI_windows_portable\python_embeded\python.exe'
```

Отдельного окружения нет. Пакеты, которых нет в ComfyUI, ставятся в `deps\`; `film.py`
сам добавляет эту папку в `sys.path`, поэтому само окружение ComfyUI остаётся нетронутым:

```powershell
& $py -m pip install --target 'I:\Video Generation\Tools\comfy-film\deps' opencv-python-headless
```

## Кто как сюда попадает

- **DSH:** `%USERPROFILE%\.dsh\skills\comfy-film-dsh` и `living-paintings` — junction'ы на
  `Tools\skills\`.
- **Codex:** `%USERPROFILE%\.codex\skills\comfy-film\` содержит `SKILL.md` (копия из
  `Tools\skills\comfy-film\SKILL.md`) и junction'ы `scripts\`, `assets\` на `Tools\comfy-film\`.
  `h3-prompt-writing` и `living-paintings` в Codex — тоже junction'ы на `Tools\skills\`.

Всё это восстанавливается одной командой:

```powershell
powershell -ExecutionPolicy Bypass -File 'I:\Video Generation\Tools\install.ps1'
```

Правила:

1. Править код и тексты скиллов только в `Tools\`. Junction — это тот же файл, но
   канонический путь в документации остаётся один.
2. Не копировать `scripts\` в другие места: расхождение версий уже случалось один раз.
3. Удаление или переименование `comfy-film\scripts\` / `comfy-film\assets\` ломает
   Codex-скилл — junction станет битым, лечится повторным `install.ps1`.
4. `machine.json` и `youtube.json` — локальные файлы, в git их нет. Шаблоны:
   `machine.example.json`, `youtube.example.json`.

## Язык панелей

Все прогресс-панели и страница просмотра по умолчанию английские. Если разговор с пользователем
идёт по-русски, панель должна быть русской:

```powershell
$env:COMFY_FILM_LANG = 'ru'   # одну строку перед film run; панель наследует переменную
```

Приоритет: `--lang` → `COMFY_FILM_LANG` → английский. Ключ `--lang ru` принимают `progress.py`,
`upscale_progress.py` и `image-progress.py`; у `serve-media.py` и у уже открытой панели язык
меняется в URL — `?lang=ru` / `?lang=en`. Запущенная панель держит тот язык, с которым её
стартовали, но `film run` перезапускает её, если запрошенный язык другой.

## Установка на чистой машине

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File 'I:\Video Generation\Tools\setup\install-comfy.ps1' -Modes video,long -Check
```

`-Check` печатает GPU, драйвер, RAM, свободное место и список недостающих моделей — ничего не
скачивает. Без `-Check` ставит ComfyUI 0.43.0 portable, пять паков нод (пины коммитов, git не нужен),
модели под выбранные режимы, FFmpeg (если его нет) и пишет `comfy-film\assets\machine.json`.
Докачка продолжается с места обрыва; уже установленное и уже скачанные модели пропускаются.

| Группа режимов | Загрузка |
|---|---|
| `video` или `long` | ~39 ГБ |
| `+ refs` | +20 ГБ (чекпойнт Ref2VA) |
| `+ lipsync` | +32 ГБ (Singularity + апскейлер) |

Нужны NVIDIA (RTX 20-й серии и новее, от 8 ГБ), драйвер 580+, 32 ГБ RAM, 40–100 ГБ диска.
Каталог с URL и размерами — `setup\catalog.json`; подробности — `skills\comfy-film-dsh\references\install.md`.

## Режимы

| Режим | Что делает | Чем запускать |
|---|---|---|
| `video` | одно видео по первому кадру или по первому и последнему | `film.py` |
| `long` | сцены, где каждая продолжает предыдущую (`--guide prev --last`) | `film.py` |
| `refs` | персонаж и место по 1–9 картинкам (`--ref2va`) | `film.py` |
| `lipsync` | персонаж говорит или поёт под ваше аудио | `lipsync.py` |

Lipsync — отдельный вход: длина видео берётся из аудио, результат кладётся в `clips\lipsync-000N.mp4`:

```powershell
& $py 'I:\Video Generation\Tools\comfy-film\scripts\lipsync.py' `
    --audio voice.mp3 --ref face.png --prompt-file lipsync.txt `
    --project 'I:\Video Generation\Projects\<фильм>'
```

## Запуск ComfyUI

Сервер стартует сам при `film.py run` / `start` по `argv` из `machine.json`:

| Флаг | Зачем |
|---|---|
| `--disable-auto-launch` | не открывать UI в браузере при старте |
| `--windows-standalone-build` | обязателен для портативной сборки |
| `--listen 127.0.0.1 --port 8188` | только локально, порт должен совпадать с `server` |

Без `--disable-auto-launch` ComfyUI открывает вкладку на каждом автоматическом прогоне.
Проверять флаги нужно на живом процессе, а не в конфиге:

```powershell
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -like '*ComfyUI*main.py*' } |
    ForEach-Object { $_.CommandLine }
```

Перезапуск после установки нод или правки флагов:

```powershell
$p = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
     Where-Object { $_.CommandLine -like '*ComfyUI*main.py*' }
if ($p) { Stop-Process -Id $p.ProcessId -Force }
& $py 'I:\Video Generation\Tools\comfy-film\scripts\film.py' start --project 'I:/Video Generation/<...>'
```

## Проверка после правок

```powershell
& $py 'I:\Video Generation\Tools\comfy-film\tests\test_pipeline.py'          # 10 тестов, ~13 с
& $py 'I:\Video Generation\Tools\comfy-film\scripts\film.py' status --project <любой проект>
& $py "$env:USERPROFILE\.codex\skills\comfy-film\scripts\film.py" status --project <любой проект>   # проверка junction
```

## Выпуск

Финальный файл: `<name>-final-vN.mp4`, H.264 `yuv420p`, AAC, `+faststart`, декод проверен —
через `comfy-film\scripts\finalize.py` или обёртку
`skills\comfy-film-dsh\scripts\finalize_delivery.py`. Публикация — `comfy-film\scripts\youtube.py`,
метаданные в `<project>\youtube.json`.
