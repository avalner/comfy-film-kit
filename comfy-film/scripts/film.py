"""Local ComfyUI film controller. No language-model calls. Run --help for commands."""
from __future__ import annotations
import argparse
import contextlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

HERE = Path(__file__).resolve().parent

# Optional local dependency folder next to scripts/ (e.g. opencv for optical joins),
# so the pipeline runs on the ComfyUI embedded Python without touching its environment.
_DEPS = HERE.parent / "deps"
if _DEPS.is_dir() and str(_DEPS) not in sys.path:
    sys.path.insert(0, str(_DEPS))


class FilmError(Exception):
    pass


class ApiError(FilmError):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp-" + uuid.uuid4().hex)
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def emit(value):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    print(json.dumps(value, ensure_ascii=False), flush=True)


def run_process(args):
    p = subprocess.run([str(x) for x in args], capture_output=True, encoding="utf-8", errors="replace")
    if p.returncode:
        raise FilmError(p.stderr[-4000:] or p.stdout[-1000:] or f"Command failed: {args[0]}")
    return p.stdout


def progress_panel(root):
    """Start (or reuse) the read-only progress panel and return its local URL.

    Runs automatically on every `run` so the URL is always part of the command
    output; a panel failure must never block generation.
    """
    try:
        p = subprocess.run([sys.executable, str(HERE / "progress.py"), "--project", str(root)],
                           capture_output=True, encoding="utf-8", errors="replace", timeout=30)
        if p.returncode == 0:
            return json.loads(p.stdout.strip().splitlines()[-1]).get("url")
    except Exception:
        pass
    try:
        return read(Path(root) / ".pipeline" / "progress-server.json").get("url")
    except Exception:
        return None


def defaults():
    for p in [HERE / "machine.json", HERE.parent / "assets" / "machine.json"]:
        if p.exists():
            return read(p)
    return {"server": "http://127.0.0.1:8188", "ffmpeg": "ffmpeg", "ffprobe": "ffprobe"}


def api(config, route, payload=None, timeout=30):
    body = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(config["server"].rstrip("/") + route, data=body,
                                 headers={"Content-Type": "application/json"} if body else {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise ApiError(e.code, f"ComfyUI HTTP {e.code}: {e.read().decode(errors='replace')[:2000]}") from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise FilmError(f"ComfyUI unavailable: {e}") from e


def pid_alive(pid):
    if not pid or pid < 1:
        return False
    if os.name == "nt":
        import ctypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return ctypes.get_last_error() == 5  # Access denied: do not assume dead.
        try:
            code = ctypes.c_ulong()
            return bool(kernel.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def server_ready(config):
    try:
        q = api(config, "/queue", timeout=2)
        if not isinstance(q, dict) or not {"queue_running", "queue_pending"} <= set(q):
            raise FilmError("The server responds but does not look like ComfyUI; refusing to launch another process")
        return True
    except ApiError:
        raise
    except FilmError as e:
        if "ComfyUI unavailable" not in str(e):
            raise
        return False
    except OSError:
        return False


def ensure_server(config):
    if server_ready(config):
        return {"status": "already_running", "server": config["server"]}
    machine = defaults()
    startup = config.get("startup")
    if startup is None and config["server"].rstrip("/") == machine.get("server", "").rstrip("/"):
        startup = machine.get("startup")  # Older projects inherit this machine's launcher.
    if not startup or not startup.get("enabled", False):
        raise FilmError("ComfyUI is offline and autostart is not configured; start it or configure machine.json startup")
    if startup.get("server", config["server"]).rstrip("/") != config["server"].rstrip("/"):
        raise FilmError("The autostart launcher belongs to another server URL/port; configure startup.server and argv together")
    url = urllib.parse.urlparse(config["server"])
    if url.hostname not in ["127.0.0.1", "localhost", "::1"]:
        raise FilmError("Autostart only launches local ComfyUI; remote servers must be started on their host")
    argv = startup.get("argv", [])
    cwd = Path(startup.get("cwd", ".")).resolve()
    if not argv or not Path(argv[0]).is_file() or not cwd.is_dir():
        raise FilmError("Invalid ComfyUI startup executable or working directory")
    logs = Path(startup["log_dir"]).resolve()
    logs.mkdir(parents=True, exist_ok=True)
    lock, record = logs / "startup.lock", logs / "server-process.json"
    deadline = time.monotonic() + startup.get("timeout", 300)
    held = False
    process = None
    launched = False
    try:
        while not held:
            if server_ready(config):
                return {"status": "already_running", "server": config["server"]}
            try:
                fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, str(os.getpid()).encode())
                os.close(fd)
                held = True
            except FileExistsError:
                try:
                    owner = int(lock.read_text())
                except (ValueError, FileNotFoundError):
                    owner = os.getpid()  # A concurrent owner may still be writing the file.
                if not pid_alive(owner):
                    lock.unlink(missing_ok=True)
                    continue
                if time.monotonic() >= deadline:
                    raise FilmError(f"Another controller is starting ComfyUI; timed out waiting. Logs: {logs}")
                time.sleep(2)
        if server_ready(config):
            return {"status": "already_running", "server": config["server"]}
        prior = read(record) if record.exists() else {}
        same = prior.get("argv") == argv and prior.get("server") == config["server"]
        log = Path(prior.get("log", str(logs / "comfyui.log")))
        if not same or not pid_alive(prior.get("pid")):
            log = logs / ("comfyui-" + time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(2) + ".log")
            flags = (subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP) if os.name == "nt" else 0
            with log.open("ab", buffering=0) as stream:
                # Console codepages (cp1251 on this host) kill custom nodes that print emoji at import:
                # SeedVR2's compatibility check raises UnicodeEncodeError and takes startup down with it.
                env = dict(os.environ)
                env.setdefault("PYTHONUTF8", "1")
                env.setdefault("PYTHONIOENCODING", "utf-8")
                process = subprocess.Popen(argv, cwd=cwd, stdin=subprocess.DEVNULL, stdout=stream, stderr=subprocess.STDOUT,
                                           creationflags=flags, start_new_session=os.name != "nt", env=env)
            write(record, {"pid": process.pid, "argv": argv, "server": config["server"], "log": str(log), "started": time.time()})
            launched = True
        while True:
            if server_ready(config):
                return {"status": "started" if launched else "ready", "server": config["server"], "log": str(log)}
            if process is not None and process.poll() is not None:
                tail = log.read_bytes()[-1600:].decode(errors="replace") if log.exists() else ""
                raise FilmError(f"ComfyUI exited with code {process.returncode}; log: {log}\n{tail}")
            if time.monotonic() >= deadline:
                raise FilmError(f"ComfyUI not ready before timeout; its process was not killed. Log: {log}")
            time.sleep(2)
    finally:
        if held:
            lock.unlink(missing_ok=True)


def upload(config, path, subfolder):
    path = Path(path)
    boundary = uuid.uuid4().hex
    parts = []
    for k, v in {"type": "input", "subfolder": subfolder, "overwrite": "false"}.items():
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode())
    name = uuid.uuid4().hex + path.suffix.lower()
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="{name}"\r\nContent-Type: image/png\r\n\r\n'.encode())
    parts.extend([path.read_bytes(), f"\r\n--{boundary}--\r\n".encode()])
    req = urllib.request.Request(config["server"].rstrip("/") + "/upload/image", data=b"".join(parts),
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        result = json.load(r)
    return "/".join(x for x in [result.get("subfolder", ""), result["name"]] if x)


def probe(config, path):
    d = json.loads(run_process([config["ffprobe"], "-v", "error", "-show_streams", "-show_format", "-of", "json", path]))
    v = next((s for s in d["streams"] if s["codec_type"] == "video"), None)
    if not v:
        raise FilmError(f"No video in {path}")
    n, den = v.get("avg_frame_rate", "0/1").split("/")
    return {"width": v["width"], "height": v["height"], "fps": float(n) / max(float(den), 1),
            "duration": float(d["format"].get("duration", v.get("duration", 0))),
            "frames": int(v["nb_frames"]) if str(v.get("nb_frames", "")).isdigit() else None,
            "audio": any(s["codec_type"] == "audio" for s in d["streams"])}


@contextlib.contextmanager
def project_lock(root):
    root = Path(root).resolve()
    lock = root / ".pipeline" / "lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as e:
        raise FilmError(f"Project is locked. If its process has stopped, run unlock --project {root}") from e
    try:
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        yield
    finally:
        lock.unlink(missing_ok=True)


def load_project(root):
    root = Path(root).resolve()
    path = root / "film.json"
    if not path.exists():
        raise FilmError(f"Project missing: {path}; run init first")
    return root, read(path)


def save(root, project):
    write(root / "film.json", project)


def segment(project, number=None):
    if not project["segments"]:
        raise FilmError("No segments; run add or import first")
    number = number or len(project["segments"])
    if number < 1 or number > len(project["segments"]):
        raise FilmError(f"Unknown segment {number}")
    return project["segments"][number - 1]


def local(root, name):
    return root / name


def artifact(root, path):
    return str(Path(path).resolve().relative_to(root)).replace("\\", "/")


def frame(config, source, dest, which, scale=2):
    """Decode at most the final two seconds, not the whole film in reverse."""
    from PIL import Image, ImageFilter
    source, dest = Path(source), Path(dest)
    info = probe(config, source)
    temp = dest.with_name(dest.stem + ".raw.png")
    cmd = [config["ffmpeg"], "-v", "error", "-y"]
    if which == "last":
        cmd += ["-sseof", str(-min(2, info["duration"]))]
    cmd += ["-i", source]
    if which == "last":
        cmd += ["-vf", "reverse"]
    cmd += ["-frames:v", "1", temp]
    dest.parent.mkdir(parents=True, exist_ok=True)
    run_process(cmd)
    try:
        with Image.open(temp) as im:
            im = im.convert("RGB")
            if scale != 1:
                im = im.resize((im.width * scale, im.height * scale), Image.Resampling.LANCZOS)
                im = im.filter(ImageFilter.UnsharpMask(radius=1.2, percent=35, threshold=3))
            im.save(dest)
    finally:
        temp.unlink(missing_ok=True)
    return info


def fit_image(config, source, dest):
    """Identical cover-crop for BOTH keyframes; never stretch their proportions."""
    from PIL import Image, ImageOps
    with Image.open(source) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        im = ImageOps.fit(im, (config["width"], config["height"]), method=Image.Resampling.LANCZOS, centering=(.5, .5))
        im.save(dest)


def identify_bindings(graph):
    def unique(cls):
        ids = [k for k, v in graph.items() if v.get("class_type") == cls]
        if len(ids) != 1:
            raise FilmError(f"Expected one {cls}, found {len(ids)}. Supply --bindings JSON for a custom graph.")
        return ids[0]
    h3, saver = unique("MiniMaxH3ImageToVideo"), unique("SaveVideo")
    first = graph[h3]["inputs"].get("first_frame")
    last = graph[h3]["inputs"].get("last_frame")
    if not isinstance(first, list) or not isinstance(last, list):
        raise FilmError("Template needs first_frame and last_frame image connections")
    return {"generator": h3, "save": saver, "first": first[0], "last": last[0]}


def init_project(args):
    root = Path(args.project).resolve()
    root.mkdir(parents=True, exist_ok=True)
    if (root / "film.json").exists():
        raise FilmError("film.json already exists; existing project has not been changed")
    config = defaults()
    template = Path(args.workflow) if args.workflow else HERE.parent / "assets" / "workflow-api.json"
    if not template.exists():
        template = HERE / "workflow-api.json"
    graph = read(template)
    if "prompt" in graph:
        graph = graph["prompt"]
    if not isinstance(graph, dict) or not graph or any(not isinstance(v, dict) or "class_type" not in v or "inputs" not in v for v in graph.values()):
        raise FilmError("Use an API-format workflow JSON, not the graphical editor's nodes/links JSON")
    bindings = read(args.bindings) if args.bindings else identify_bindings(graph)
    for k in ["server", "ffmpeg", "ffprobe"]:
        if getattr(args, k, None):
            config[k] = getattr(args, k)
    config.update(width=args.width, height=args.height, fps=args.fps, quality=args.quality,
                  audio=args.audio, music=args.music, segment_seconds=args.seconds)
    if not 4 <= args.seconds <= 15:
        raise FilmError("Default segment duration must be 4–15 seconds")
    if args.audio == "silent" and args.music == "generated":
        raise FilmError("Generated music requires --audio generated; use --music none or later for silent output")
    if args.quality != "workflow":
        switches = [k for k, v in graph.items() if v.get("class_type") == "PrimitiveBoolean"]
        switch = bindings.get("turbo") or (switches[0] if len(switches) == 1 else None)
        if switch not in graph:
            raise FilmError("Quality selector ambiguous; provide bindings.turbo or --quality workflow for a custom graph")
        graph[switch]["inputs"]["value"] = args.quality == "turbo"
    if args.width % 32 or args.height % 32 or args.fps != 24:
        raise FilmError("This H3 template requires dimensions divisible by 32 and 24 fps")
    data = root / ".pipeline"
    data.mkdir(exist_ok=True)
    write(data / "workflow-api.json", graph)
    p = {"version": 1, "id": uuid.uuid4().hex, "title": args.title or root.name,
         "config": config, "bindings": bindings, "segments": [], "joins": {}, "exports": []}
    save(root, p)
    return {"project": str(root), "config": config, "next": "add"}


PREVIEW_CANVAS = (384, 672)


def preview_project(args, root, p):
    """Create (or report) a low-resolution sibling of this film for staging tests.

    The previz shares the prompt files and boards but not the canvas: an H3 guide clip is bound to
    its project's resolution, so a preview take can never continue a master take. It exists to settle
    staging, timing and whether the model can perform a beat at all — 5 s at 384x672 costs ~30 s
    against ~10 min for a 10 s native take.
    """
    width = args.width or PREVIEW_CANVAS[0]
    height = args.height or PREVIEW_CANVAS[1]
    seconds = args.seconds or min(5.0, float(p["config"].get("segment_seconds", 5.0)))
    if width % 32 or height % 32:
        raise FilmError("The preview canvas must be divisible by 32")
    if not 4 <= seconds <= 15:
        raise FilmError("Preview segment duration must be 4–15 seconds")
    name = args.name or f"{root.name} previz {width}x{height}"
    target = (root.parent / name).resolve()
    if (target / "film.json").exists():
        return {"project": str(target), "status": "exists", "canvas": f"{width}x{height}",
                "next": "add", "hint": "Existing previz left untouched; pass --name for a new one"}
    template = root / ".pipeline" / "workflow-api.json"
    if not template.exists():
        raise FilmError("The master project has no workflow-api.json; run film doctor on it first")
    target.mkdir(parents=True, exist_ok=True)
    data = target / ".pipeline"
    data.mkdir(exist_ok=True)
    write(data / "workflow-api.json", read(template))
    config = dict(p["config"])
    config.update(width=width, height=height, segment_seconds=seconds)
    q = {"version": 1, "id": uuid.uuid4().hex,
         "title": f"{p['title']} — previz {width}x{height}",
         "config": config, "bindings": dict(p["bindings"]),
         "segments": [], "joins": {}, "exports": [], "preview_of": str(root)}
    save(target, q)
    return {"project": str(target), "status": "created", "canvas": f"{width}x{height}",
            "seconds": seconds, "master": str(root),
            "hint": "add the master's boards and prompt files here; approve staging, then re-shoot at native",
            "next": "add"}


def ensure_idle(project):
    active = [s["number"] for s in project["segments"] if s["status"] in ["submitting", "running"]]
    if active:
        raise FilmError(f"Segments still active: {active}; wait or recover before modifying the sequence")


def copy_input(root, source, dest):
    source = Path(source).resolve()
    if not source.is_file():
        raise FilmError(f"File missing: {source}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    if source != dest.resolve():
        shutil.copy2(source, dest)
        if dest.exists() and not os.access(dest, os.W_OK):
            os.chmod(dest, 0o666)  # copy2 keeps a read-only source's mode; the pipeline must own its copies
    return artifact(root, dest)


def guide_skip(config, path, frames, tail_trim_frames=0):
    """First frame index of the guide clip inside an existing clip, honouring its tail trim."""
    info = probe(config, path)
    total = info["frames"] or int(round(info["duration"] * info["fps"]))
    skip = total - int(tail_trim_frames) - int(frames)
    if skip < 0:
        raise FilmError(f"Guide needs {frames} frames + {tail_trim_frames} trimmed frames; {path} has {total}")
    return skip, total


def extend_graph(root, p, s, cfg):
    """API graph for continuation: the tail of the previous clip is anchored at frame 0 as a moving guide.

    A last keyframe may be supplied too: the guide carries the motion in from the previous clip and
    the last frame pulls the take to a designed pose, so the ending is not left to the model.
    """
    graph = read(root / ".pipeline" / "workflow-api.json")
    gen_id = p["bindings"]["generator"]
    gen = graph[gen_id]["inputs"]
    gen.pop("first_frame", None)
    if "last" not in s:
        gen.pop("last_frame", None)
    for label in ("first",):
        node = p["bindings"].get(label)
        if node in graph:
            graph.pop(node)
    guider = next(k for k, v in graph.items() if v["class_type"] == "BasicGuider")
    vaes = [k for k, v in graph.items() if v["class_type"] == "VAELoader"]
    video_vae = next((k for k in vaes if "video" in str(graph[k]["inputs"].get("vae_name", "")).lower()),
                     vaes[0] if vaes else None)
    audio_vae = next((k for k in vaes if "audio" in str(graph[k]["inputs"].get("vae_name", "")).lower()), None)
    if not video_vae:
        raise FilmError("Continuation needs a video VAE loader in the workflow template")
    guide = s["guide"]
    graph["900"] = {"class_type": "VHS_LoadVideoPath",
                    "inputs": {"video": str((root / guide["file"]).resolve()),
                               "force_rate": float(cfg.get("fps", 24)),
                               "custom_width": int(cfg["width"]), "custom_height": int(cfg["height"]),
                               "frame_load_cap": int(guide["frames"]),
                               "skip_first_frames": int(guide["skip"]),
                               "select_every_nth": 1}}
    inputs = {"positive": [gen_id, 0], "latent": [gen_id, 1],
              "vae": [video_vae, 0], "image": ["900", 0], "frame_idx": 0}
    if audio_vae:
        inputs["audio_vae"] = [audio_vae, 0]
        inputs["audio"] = ["900", 2]
    graph["901"] = {"class_type": "MiniMaxH3AddGuide", "inputs": inputs}
    graph[guider]["inputs"]["conditioning"] = ["901", 0]
    return graph


def add_segment(args, root, p):
    ensure_idle(p)
    if args.command == "import" and getattr(args, "replace_rejected", False):
        if not p["segments"] or p["segments"][-1]["status"] != "rejected":
            raise FilmError("Replacement import requires the latest segment to be rejected")
        s = p["segments"][-1]
        if s.get("accepted"):
            raise FilmError("Cannot replace accepted media")
        info = probe(p["config"], args.file)
        dest = root / ".pipeline" / "segments" / f'{s["number"]:04d}' / ("import-" + uuid.uuid4().hex[:8] + ".mp4")
        prior = {k: s[k] for k in ("review", "media", "rejection") if k in s}
        s.setdefault("replaced_candidates", []).append(prior)
        s.update(review=copy_input(root, args.file, dest), media=info, status="review", trim_head=0., trim_tail=0.)
        save(root, p)
        return {"segment": s["number"], "status": "review", "mode": "import-replacement", "next": "accept"}
    if p["segments"] and p["segments"][-1]["status"] != "accepted":
        raise FilmError("Accept the previous segment before adding the next one")
    number = len(p["segments"]) + 1
    folder = root / ".pipeline" / "segments" / f"{number:04d}"
    folder.mkdir(parents=True, exist_ok=True)
    s = {"number": number, "status": "draft", "attempts": [], "trim_head": 0., "trim_tail": 0.}
    if args.command == "import":
        info = probe(p["config"], args.file)
        s.update(review=copy_input(root, args.file, folder / "import-review.mp4"), media=info, status="review")
    else:
        seconds = args.seconds if args.seconds is not None else p["config"].get("segment_seconds", 10)
        if not 4 <= seconds <= 15:
            raise FilmError("H3 segment duration must be 4–15 seconds; assemble as many segments as needed")
        s["seconds"] = seconds
        s["prompt"] = copy_input(root, args.prompt_file, folder / "prompt.txt")
        if getattr(args, "text_only", False):
            if args.first or args.last or args.loop or args.guide:
                raise FilmError("--text-only cannot be combined with frame or guide inputs")
            s["text_only"] = True
        elif args.first:
            s["first"] = copy_input(root, args.first, folder / ("first-source" + Path(args.first).suffix.lower()))
        elif p["segments"] and not getattr(args, "guide", None):
            previous = p["segments"][-1]
            dest = folder / "first-from-previous-upscaled.png"
            frame(p["config"], root / previous["accepted"], dest, "last")
            s["first"] = artifact(root, dest)
        elif not getattr(args, "guide", None):
            raise FilmError("The first segment needs --first")
        if args.last:
            s["last"] = copy_input(root, args.last, folder / ("last-source" + Path(args.last).suffix.lower()))
        elif args.loop:
            if not p["segments"]:
                raise FilmError("--loop requires an earlier accepted segment")
            dest = folder / "last-loop-upscaled.png"
            frame(p["config"], root / p["segments"][0]["accepted"], dest, "first")
            s["last"] = artifact(root, dest)
        if getattr(args, "guide", None):
            if args.first or args.loop:
                raise FilmError("--guide continues a clip; do not combine it with --first or --loop")
            if not p["segments"]:
                raise FilmError("--guide needs an earlier accepted clip to continue")
            frames = int(args.guide_frames)
            if frames not in (5, 22, 39):
                raise FilmError("--guide-frames must be 5, 22 or 39 (H3's 17k+5 clip grid)")
            previous = p["segments"][-1]
            source = root / previous["accepted"] if args.guide == "prev" else Path(args.guide)
            dest = folder / "guide-source.mp4"
            s["guide"] = {"file": copy_input(root, source, dest), "frames": frames}
            skip, total = guide_skip(p["config"], root / s["guide"]["file"], frames,
                                     round(previous.get("trim_tail", 0) * p["config"].get("fps", 24)))
            s["guide"]["skip"] = skip
            s["guide"]["source_frames"] = total
            s["trim_head"] = frames / float(p["config"].get("fps", 24))
        if getattr(args, "ref2va", None):
            sources = list(args.ref2va)
            if not 1 <= len(sources) <= 9:
                raise FilmError("--ref2va takes 1-9 pictures")
            images = []
            for i, path in enumerate(sources):
                source = Path(path)
                if not source.is_file():
                    raise FilmError(f"No such reference picture: {path}")
                images.append(copy_input(root, source, folder / f"ref2va-{i}{source.suffix.lower()}"))
            s["ref2va"] = {"images": images, "steps": int(args.ref2va_steps),
                           "image_size": args.ref2va_size}
            if args.ref2va_model:
                s["ref2va"]["model"] = args.ref2va_model
            if args.ref2va_lora:
                s["ref2va"]["lora"] = args.ref2va_lora
    p["segments"].append(s)
    save(root, p)
    if args.command == "import":
        mode = "import"
    elif s.get("guide") and "last" in s:
        mode = "guide+last"
    elif s.get("guide"):
        mode = "guide"
    elif "first" in s and "last" in s:
        mode = "fl2va"
    elif "first" in s and "last" not in s:
        mode = "i2va"
    elif "last" in s:
        mode = "l2va"
    else:
        mode = "t2va"
    if s.get("ref2va"):
        mode = "ref2va+" + mode
    result = {"segment": number, "status": s["status"], "mode": mode,
              "next": "accept" if s["status"] == "review" else "run",
              "first_frame": str(root / s["first"]) if "first" in s else None,
              "guide": s.get("guide")}
    if mode == "i2va" and len(p["segments"]) > 1:
        result["hint"] = ("I2VA from the previous last frame: the take eases out of a still. For a beat that "
                          "continues motion (fall, run, spin) use --guide prev instead.")
    elif mode == "fl2va" and len(p["segments"]) > 1:
        result["hint"] = "FL2VA: both ends are fixed, the take decelerates into the last frame."
    return result


def prune(graph, output):
    keep = set()
    def visit(key):
        if key in keep:
            return
        keep.add(key)
        for v in graph[key].get("inputs", {}).values():
            if isinstance(v, list) and len(v) == 2 and str(v[0]) in graph and isinstance(v[1], int):
                visit(str(v[0]))
    visit(output)
    return {k: {"class_type": graph[k]["class_type"], "inputs": graph[k]["inputs"]} for k in graph if k in keep}


_LORA_CACHE = {}


def server_loras(cfg):
    """Names ComfyUI will accept in LoraLoaderModelOnly, from the live /object_info."""
    key = cfg["server"].rstrip("/")
    if key not in _LORA_CACHE:
        info = api(cfg, "/object_info/LoraLoaderModelOnly")
        names = ((info.get("LoraLoaderModelOnly") or {}).get("input") or {}).get("required", {}).get("lora_name")
        _LORA_CACHE[key] = list(names[0]) if names else []
    return _LORA_CACHE[key]


def resolve_adapters(args, s, cfg):
    """Adapter specs for this take: --lora on the command line, else the ones already recorded."""
    specs = list(getattr(args, "lora", None) or [])
    if getattr(args, "no_lora", False):
        return []
    if not specs:
        return s.get("adapters") or []
    strength = getattr(args, "lora_strength", None)
    if strength is None:
        strength = 1.0
    if not 0.0 <= strength <= 2.0:
        raise FilmError("--lora-strength must be between 0.0 and 2.0")
    available = server_loras(cfg)
    out = []
    for raw in specs:
        name = Path(raw).name if (Path(raw).is_absolute() or Path(raw).exists()) else raw
        if available and name not in available:
            raise FilmError(f"ComfyUI has no LoRA named {name!r}; available: {', '.join(sorted(available))}")
        out.append({"name": name, "strength": float(strength)})
    return out


def apply_adapters(graph, adapters):
    """Chain LoraLoaderModelOnly nodes onto the model link the sampler consumes."""
    guider = next((v for v in graph.values() if v["class_type"] == "BasicGuider"), None)
    if guider is None:
        raise FilmError("No BasicGuider in the workflow; cannot attach an adapter")
    source = guider["inputs"].get("model")
    if not isinstance(source, list) or len(source) != 2:
        raise FilmError("BasicGuider model input is not a link; cannot attach an adapter")
    consumers = [(node, key) for node in graph.values() for key, value in node["inputs"].items()
                 if isinstance(value, list) and value == source]
    current = list(source)
    made = []
    for i, spec in enumerate(adapters, 1):
        node_id = f"film-adapter-{i:02d}"
        graph[node_id] = {"class_type": "LoraLoaderModelOnly", "inputs": {
            "model": list(current), "lora_name": spec["name"], "strength_model": float(spec["strength"])}}
        current = [node_id, 0]
        made.append(node_id)
    for node, key in consumers:
        node["inputs"][key] = list(current)
    return made


def apply_reference_mode(root, p, s, graph, folder):
    """Opt-in per-segment Ref2VA; retain continuation/end anchors as AddGuide nodes."""
    ref = s.get("ref2va")
    if not ref:
        return graph
    images = ref.get("images", [])
    if not 1 <= len(images) <= 9:
        raise FilmError("Ref2VA needs 1–9 reference images")
    gen_id = p["bindings"]["generator"]
    old = graph[gen_id]["inputs"]
    vae = old.get("vae")
    if not vae:
        raise FilmError("Ref2VA requires video VAE")
    graph[gen_id]["class_type"] = "MiniMaxH3ReferenceToVideo"
    inputs = {k: old[k] for k in ("clip", "vae", "prompt", "width", "height", "length")}
    inputs["ref_image_size"] = ref.get("image_size", "match")
    for i, source in enumerate(images):
        node = "ref-image-" + str(i)
        name = upload(p["config"], root / source, "comfy_film/" + p["id"])
        graph[node] = {"class_type": "LoadImage", "inputs": {"image": name}}
        inputs["ref_images.ref_image_" + str(i)] = [node, 0]
    graph[gen_id]["inputs"] = inputs
    loaders = [v for v in graph.values() if v["class_type"] == "UNETLoader"]
    if len(loaders) != 1:
        raise FilmError("Ref2VA model loader is ambiguous")
    if ref.get("model"):
        loaders[0]["inputs"]["unet_name"] = ref["model"]
    model_link = next([k, 0] for k, v in graph.items() if v is loaders[0])
    if ref.get("lora"):
        graph["ref-turbo-lora"] = {"class_type": "LoraLoaderModelOnly", "inputs": {
            "model": model_link, "lora_name": ref["lora"], "strength_model": 1.0}}
        graph["ref-turbo-shift"] = {"class_type": "MiniMaxH3SigmaShift", "inputs": {
            "model": ["ref-turbo-lora", 0], "shift_video": 12.0, "shift_audio": 3.0}}
        model_link = ["ref-turbo-shift", 0]
    # Ref2VA must never inherit the unrelated FL2VA Turbo branch.
    for node in graph.values():
        if node["class_type"] == "BasicGuider":
            node["inputs"]["model"] = model_link
        if node["class_type"] == "BasicScheduler":
            node["inputs"]["model"] = model_link
            node["inputs"]["steps"] = int(ref.get("steps", 20))
        if ref.get("lora") and node["class_type"] == "KSamplerSelect":
            node["inputs"]["sampler_name"] = "euler"
    # Reference conditioning and keyframe anchoring are separate model inputs.
    guider = next(v for v in graph.values() if v["class_type"] == "BasicGuider")
    previous = guider["inputs"]["conditioning"]
    for label, frame_idx in (("first", 0), ("last", -1)):
        if label not in s:
            continue
        node = "ref-anchor-" + label
        graph[node] = {"class_type": "MiniMaxH3AddGuide", "inputs": {
            "positive": previous, "latent": [gen_id, 1], "vae": vae,
            "image": [p["bindings"][label], 0], "frame_idx": frame_idx}}
        previous = [node, 0]
    guider["inputs"]["conditioning"] = previous
    return graph


def submit(args, root, p):
    s = segment(p, args.segment)
    if s["status"] not in ["draft", "rejected", "failed"]:
        raise FilmError(f"Segment is {s['status']}; will not silently rerun or overwrite it")
    if s["number"] > 1 and p["segments"][s["number"] - 2]["status"] != "accepted":
        raise FilmError("Previous segment is not accepted")
    ensure_idle(p)
    cfg = p["config"]
    ensure_server(cfg)
    q = api(cfg, "/queue")
    if (q.get("queue_running") or q.get("queue_pending")) and not args.enqueue:
        raise FilmError("ComfyUI is busy; no job submitted. Use --enqueue only if adding to the queue is intended")
    folder = root / ".pipeline" / "segments" / f"{s['number']:04d}"
    if getattr(args, "first", None):
        s.setdefault("input_revisions", []).append({k: s[k] for k in ("first", "guide", "seconds", "trim_head") if k in s})
        s["first"] = copy_input(root, args.first, folder / ("first-revised-" + uuid.uuid4().hex[:8] + Path(args.first).suffix.lower()))
        s.pop("guide", None)
        s["trim_head"] = 0.
    if getattr(args, "seconds", None) is not None:
        if not 4 <= args.seconds <= 15:
            raise FilmError("H3 segment duration must be 4–15 seconds")
        s["seconds"] = args.seconds
    if args.prompt_file:
        s["prompt"] = copy_input(root, args.prompt_file, folder / "prompt.txt")
    graph = extend_graph(root, p, s, cfg) if s.get("guide") else read(root / ".pipeline" / "workflow-api.json")
    bind = p["bindings"]
    for label in ["first", "last"]:
        if label in s:
            prepared = folder / (label + "-canvas.png")
            fit_image(cfg, root / s[label], prepared)
            name = upload(cfg, prepared, "comfy_film/" + p["id"])
            graph[bind[label]]["inputs"]["image"] = name
    gen = graph[bind["generator"]]["inputs"]
    if s.get("text_only"):
        gen.pop("first_frame", None)
        gen.pop("last_frame", None)
    gen.update(prompt=(root / s["prompt"]).read_text(encoding="utf-8-sig"), width=cfg["width"], height=cfg["height"])
    n = max(5, round(s["seconds"] * 24))
    gen["length"] = n + (5 - n % 17) % 17
    if "last" not in s:
        gen.pop("last_frame", None)
    seed = args.seed if args.seed is not None else secrets.randbelow(2 ** 50)
    for node in graph.values():
        if node["class_type"] == "RandomNoise":
            node["inputs"]["noise_seed"] = seed
    attempt_id = uuid.uuid4().hex
    prefix = f"video/comfy_film/{p['id']}/segment-{s['number']:04d}-{attempt_id[:8]}"
    graph[bind["save"]]["inputs"]["filename_prefix"] = prefix
    if cfg.get("audio", "generated") == "silent":
        creators = [v for v in graph.values() if v["class_type"] == "CreateVideo"]
        if len(creators) != 1:
            raise FilmError("Silent-output binding is ambiguous in this custom workflow")
        creators[0]["inputs"].pop("audio", None)
    graph = apply_reference_mode(root, p, s, graph, folder)
    adapters = resolve_adapters(args, s, cfg)
    if adapters:
        s["adapters"] = adapters
        apply_adapters(graph, adapters)
    elif "adapters" in s:
        s.pop("adapters")
    graph = prune(graph, bind["save"])
    attempt = {"id": attempt_id, "seed": seed, "submitted_at": time.time(), "prefix": prefix,
               "client_id": "film-" + attempt_id}
    s["attempts"].append(attempt)
    s["status"] = "submitting"
    save(root, p)  # Persist uncertainty BEFORE making the non-idempotent request.
    write(folder / ("workflow-" + attempt_id[:8] + ".json"), graph)
    try:
        result = api(cfg, "/prompt", {"prompt": graph, "client_id": attempt["client_id"]}, timeout=60)
    except (FilmError, OSError) as e:
        attempt["submit_error"] = str(e)
        if isinstance(e, ApiError) and e.status in [400, 401, 403, 404, 422]:
            s["status"] = "failed"
            save(root, p)
            raise FilmError(f"ComfyUI rejected the request; fix its cause before running again. {e}") from e
        save(root, p)
        raise FilmError(f"Submission response uncertain; do not retry. Run recover. {e}") from e
    if result.get("node_errors") or not result.get("prompt_id"):
        s["status"] = "failed"
        attempt["error"] = result
        save(root, p)
        raise FilmError(f"Workflow rejected: {json.dumps(result)[:1500]}")
    attempt["prompt_id"] = result["prompt_id"]
    s["status"] = "running"
    save(root, p)
    return {"segment": s["number"], "status": "running", "prompt_id": result["prompt_id"],
            "frames": gen["length"], "actual_seconds": gen["length"] / 24,
            "progress": progress_panel(root), "next": "wait"}


def collect(root, p, s):
    if s["status"] != "running":
        return False
    attempt = s["attempts"][-1]
    h = api(p["config"], "/history/" + attempt["prompt_id"])
    entry = h.get(attempt["prompt_id"])
    if not entry:
        return False
    messages = entry.get("status", {}).get("messages", [])
    if entry.get("status", {}).get("status_str") == "error" or any(m[0] in ["execution_error", "execution_interrupted"] for m in messages):
        s["status"] = "failed"
        attempt["error"] = messages[-2:]
        save(root, p)
        raise FilmError(f"Generation failed; no automatic retry. {json.dumps(messages[-2:])[:1800]}")
    if not entry.get("status", {}).get("completed"):
        return False
    files = []
    for node in entry.get("outputs", {}).values():
        for key in ["images", "videos", "gifs"]:
            files += [f for f in node.get(key, []) if Path(f.get("filename", "")).suffix.lower() in [".mp4", ".webm", ".mov", ".mkv"]]
    if not files:
        raise FilmError("Generation completed but no supported video output was found")
    if len(files) != 1:
        raise FilmError("Multiple output videos; select the intended output before continuing")
    f = files[0]
    query = urllib.parse.urlencode({k: f.get(k, "output" if k == "type" else "") for k in ["filename", "subfolder", "type"]})
    review = root / ".pipeline" / "reviews" / f"{s['number']:04d}-{attempt['id'][:8]}.mp4"
    review.parent.mkdir(exist_ok=True)
    temp = review.with_suffix(".download")
    with urllib.request.urlopen(p["config"]["server"].rstrip("/") + "/view?" + query, timeout=120) as r, temp.open("wb") as dst:
        shutil.copyfileobj(r, dst)
    os.replace(temp, review)
    info = probe(p["config"], review)
    s.update(status="review", review=artifact(root, review), media=info)
    attempt["completed_at"] = time.time()
    save(root, p)
    return True


def wait_for(args):
    deadline = time.monotonic() + args.timeout
    _, initial = load_project(args.project)
    if segment(initial, args.segment)["status"] == "running":
        ensure_server(initial["config"])
    while True:
        with project_lock(args.project):
            root, p = load_project(args.project)
            s = segment(p, args.segment)
            if s["status"] == "running":
                collect(root, p, s)
            if s["status"] != "running":
                return summary(root, p, s)
        if time.monotonic() >= deadline:
            return {"status": "still_running", "next": "wait", "note": "No cancellation or duplicate submission"}
        time.sleep(args.poll)


def summary(root, p, s=None):
    if s:
        return {"segment": s["number"], "status": s["status"], "review": str(root / s["review"]) if "review" in s else None,
                "accepted": str(root / s["accepted"]) if "accepted" in s else None, "media": s.get("media")}
    counts = {}
    for x in p["segments"]:
        counts[x["status"]] = counts.get(x["status"], 0) + 1
    out = {"title": p["title"], "project": str(root), "config": p["config"],
           "segment_count": len(p["segments"]), "counts": counts,
           "segments": [
        {"number": x["number"], "status": x["status"], "seconds": x.get("media", {}).get("duration", x.get("seconds"))}
        for x in p["segments"][-5:]], "exports": p["exports"][-3:]}
    if p.get("preview_of"):
        out["preview_of"] = p["preview_of"]
        out["note"] = "preview project: staging and timing only; re-shoot the approved plan at native"
    return out


def recover(root, p, s):
    if s["status"] != "submitting":
        raise FilmError("recover is only for an uncertain submission")
    target = s["attempts"][-1]
    ensure_server(p["config"])
    matches = []
    q = api(p["config"], "/queue")
    for item in q.get("queue_running", []) + q.get("queue_pending", []):
        if any(n.get("inputs", {}).get("filename_prefix") == target["prefix"] for n in item[2].values()):
            matches.append(item[1])
    for pid, entry in api(p["config"], "/history?max_items=200").items():
        prompt = entry.get("prompt", [])
        if len(prompt) > 2 and any(n.get("inputs", {}).get("filename_prefix") == target["prefix"] for n in prompt[2].values()):
            matches.append(pid)
    matches = list(set(matches))
    if len(matches) != 1:
        raise FilmError(f"Found {len(matches)} matching jobs. No resubmission performed; inspect ComfyUI history")
    target["prompt_id"] = matches[0]
    s["status"] = "running"
    save(root, p)
    collect(root, p, s)
    return summary(root, p, s)


def accept(args, root, p):
    s = segment(p, args.segment)
    if s["status"] != "review":
        raise FilmError("Only a reviewed candidate can be accepted")
    dest = root / "clips" / f"segment-{s['number']:04d}.mp4"
    if dest.exists():
        raise FilmError(f"Refusing to overwrite accepted clip: {dest}")
    dest.parent.mkdir(exist_ok=True)
    shutil.copy2(root / s["review"], dest)
    s.update(status="accepted", accepted=artifact(root, dest), accepted_at=time.time())
    save(root, p)
    return summary(root, p, s)


def extract(args, root, p):
    s = segment(p, args.segment)
    if s["status"] != "accepted":
        raise FilmError("Extract continuation frames only from an accepted clip")
    name = f"segment-{s['number']:04d}-{args.which}-{args.scale}x.png"
    dest = root / "frames" / name
    frame(p["config"], root / s["accepted"], dest, args.which, args.scale)
    return {"frame": str(dest), "which": args.which, "scale": args.scale}


def inspect_segment(args, root, p):
    s = segment(p, args.segment)
    source = s.get("accepted") or s.get("review")
    if not source:
        raise FilmError("No video available to inspect yet")
    cfg = p["config"]
    info = probe(cfg, root / source)
    folder = root / ".pipeline" / "previews"
    folder.mkdir(exist_ok=True)
    paths = {}
    for kind in ["overview", "ending"]:
        dest = folder / f"segment-{s['number']:04d}-{kind}.png"
        cmd = [cfg["ffmpeg"], "-v", "error", "-y"]
        duration = info["duration"] if kind == "overview" else min(1, info["duration"])
        if kind == "ending":
            cmd += ["-sseof", str(-duration)]
        cmd += ["-i", root / source, "-vf", f"fps={4/duration},scale=240:-1,tile=4x1", "-frames:v", "1", dest]
        run_process(cmd)
        paths[kind] = str(dest)
    return {"segment": s["number"], "media": info, "previews": paths}


def doctor(root, p):
    cfg = p["config"]
    startup = ensure_server(cfg)
    versions = {}
    for key in ["ffmpeg", "ffprobe"]:
        versions[key] = run_process([cfg[key], "-version"]).splitlines()[0]
    info = api(cfg, "/object_info")
    graph = read(root / ".pipeline" / "workflow-api.json")
    missing = sorted({n["class_type"] for n in graph.values()} - set(info))
    q = api(cfg, "/queue")
    import importlib.util
    return {"server": cfg["server"], "startup": startup, "missing_node_classes": missing, "versions": versions,
            "running_jobs": len(q.get("queue_running", [])), "queued_jobs": len(q.get("queue_pending", [])),
            "pillow": importlib.util.find_spec("PIL") is not None,
            "optical_available": importlib.util.find_spec("cv2") is not None and importlib.util.find_spec("numpy") is not None}


def normalize(cfg, source, output, head, tail):
    info = probe(cfg, source)
    duration = info["duration"] - head - tail
    if duration <= 1 / cfg["fps"]:
        raise FilmError(f"Trims remove entire clip: {source}")
    args = [cfg["ffmpeg"], "-v", "error", "-y", "-ss", str(head), "-i", source]
    if not info["audio"]:
        args += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
    vf = f"scale={cfg['width']}:{cfg['height']}:force_original_aspect_ratio=decrease,pad={cfg['width']}:{cfg['height']}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={cfg['fps']},format=yuv420p,setpts=PTS-STARTPTS"
    args += ["-t", str(duration), "-vf", vf, "-map", "0:v:0", "-map", "0:a:0" if info["audio"] else "1:a:0",
             "-af", "aresample=48000,apad,asetpts=PTS-STARTPTS", "-c:v", "libx264", "-crf", "18", "-preset", "fast",
             "-c:a", "aac", "-ar", "48000", "-ac", "2", "-b:a", "192k", "-video_track_timescale", "24000", "-movflags", "+faststart", output]
    run_process(args)
    return probe(cfg, output)


def ffmpeg_piece(cfg, path, start, duration, output):
    run_process([cfg["ffmpeg"], "-v", "error", "-y", "-ss", f"{start:.9f}", "-i", path, "-t", f"{duration:.9f}",
                 "-vf", "setpts=PTS-STARTPTS", "-af", "asetpts=PTS-STARTPTS", "-c:v", "libx264", "-crf", "18", "-preset", "fast",
                 "-c:a", "aac", "-ar", "48000", "-ac", "2", "-video_track_timescale", "24000", output])


def optical_bridge(cfg, left, right, n, output, work):
    try:
        import cv2
        import numpy as np
    except ImportError as e:
        raise FilmError("Optical joins need numpy and opencv-python-headless; use cut/crossfade or install dependencies") from e
    ca, cb = cv2.VideoCapture(str(left)), cv2.VideoCapture(str(right))
    ca.set(cv2.CAP_PROP_POS_FRAMES, max(0, int(ca.get(cv2.CAP_PROP_FRAME_COUNT)) - n))
    silent = work / (output.stem + "-silent.mp4")
    w, h = cfg["width"], cfg["height"]
    writer = cv2.VideoWriter(str(silent), cv2.VideoWriter_fourcc(*"mp4v"), cfg["fps"], (w, h))
    if not writer.isOpened():
        raise FilmError("Could not open optical bridge encoder")
    y, x = np.mgrid[:h, :w].astype(np.float32)
    dis = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
    try:
        for i in range(n):
            oka, a = ca.read()
            okb, b = cb.read()
            if not oka or not okb:
                raise FilmError("Not enough frames for transition")
            t = np.float32(i / max(1, n - 1))
            t = t * t * (3 - 2 * t)
            ga, gb = cv2.cvtColor(a, cv2.COLOR_BGR2GRAY), cv2.cvtColor(b, cv2.COLOR_BGR2GRAY)
            f, r = dis.calc(ga, gb, None), dis.calc(gb, ga, None)
            wa = cv2.remap(a, x - t * f[:, :, 0], y - t * f[:, :, 1], cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT_101)
            wb = cv2.remap(b, x - (1 - t) * r[:, :, 0], y - (1 - t) * r[:, :, 1], cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT_101)
            writer.write(cv2.addWeighted(wa, 1 - float(t), wb, float(t), 0))
    finally:
        writer.release()
        ca.release()
        cb.release()
    duration = n / cfg["fps"]
    end = probe(cfg, left)["duration"]
    # Mix both equally long ambience windows without changing the video duration.
    filt = f"[1:a]atrim=start={end-duration:.9f},asetpts=PTS-STARTPTS,afade=t=out:st=0:d={duration:.9f}[a];[2:a]atrim=end={duration:.9f},asetpts=PTS-STARTPTS,afade=t=in:st=0:d={duration:.9f}[b];[a][b]amix=inputs=2:normalize=0[audio]"
    run_process([cfg["ffmpeg"], "-v", "error", "-y", "-i", silent, "-i", left, "-i", right, "-filter_complex", filt,
                 "-map", "0:v", "-map", "[audio]", "-t", str(duration), "-c:v", "libx264", "-crf", "18", "-preset", "fast",
                 "-c:a", "aac", "-ar", "48000", "-ac", "2", "-video_track_timescale", "24000", output])


def stitch(args, root, p):
    segments = p["segments"]
    if not segments or any(s["status"] != "accepted" for s in segments):
        raise FilmError("All included segments must be explicitly accepted before stitching")
    cfg = p["config"]
    export_id = time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(2)
    work = root / ".pipeline" / "exports" / export_id
    work.mkdir(parents=True)
    normalized, media = [], []
    for s in segments:
        output = work / f"normalized-{s['number']:04d}.mp4"
        info = normalize(cfg, root / s["accepted"], output, s["trim_head"], s["trim_tail"])
        normalized.append(output)
        media.append(info)
    joins = []
    for n in range(1, len(segments)):
        j = p["joins"].get(str(n), {"mode": "cut", "seconds": 0})
        count = 0 if j["mode"] == "cut" else max(2, round(j["seconds"] * cfg["fps"]))
        joins.append({"mode": j["mode"], "n": count, "seconds": count / cfg["fps"]})
    for i, info in enumerate(media):
        left = joins[i - 1]["seconds"] if i else 0
        right = joins[i]["seconds"] if i < len(joins) else 0
        if left + right >= info["duration"] - 1 / cfg["fps"]:
            raise FilmError(f"Transitions consume segment {i + 1}; shorten them or reduce trimming")
    pieces = []
    for i, path in enumerate(normalized):
        head = joins[i - 1]["seconds"] if i else 0
        tail = joins[i]["seconds"] if i < len(joins) else 0
        body = path
        if head or tail:
            body = work / f"body-{i+1:04d}.mp4"
            ffmpeg_piece(cfg, path, head, media[i]["duration"] - head - tail, body)
        pieces.append(body)
        if i >= len(joins) or not joins[i]["n"]:
            continue
        j = joins[i]
        bridge = work / f"bridge-{i+1:04d}.mp4"
        if j["mode"] == "optical":
            optical_bridge(cfg, path, normalized[i + 1], j["n"], bridge, work)
        else:
            d = j["seconds"]
            filt = f"[0:v]trim=start={media[i]['duration']-d:.9f},setpts=PTS-STARTPTS,settb=AVTB[a];[1:v]trim=end={d:.9f},setpts=PTS-STARTPTS,settb=AVTB[b];[a][b]blend=all_expr='A*(1-T/{d})+B*T/{d}',format=yuv420p[v];[0:a]atrim=start={media[i]['duration']-d:.9f},asetpts=PTS-STARTPTS,afade=t=out:st=0:d={d}[aa];[1:a]atrim=end={d:.9f},asetpts=PTS-STARTPTS,afade=t=in:st=0:d={d}[bb];[aa][bb]amix=inputs=2:normalize=0[au]"
            run_process([cfg["ffmpeg"], "-v", "error", "-y", "-i", path, "-i", normalized[i+1], "-filter_complex", filt,
                         "-map", "[v]", "-map", "[au]", "-t", str(d), "-c:v", "libx264", "-crf", "18", "-preset", "fast",
                         "-c:a", "aac", "-ar", "48000", "-ac", "2", "-video_track_timescale", "24000", bridge])
        pieces.append(bridge)
    listing = work / "concat.txt"
    listing.write_text("\n".join("file '" + str(x.resolve()).replace("\\", "/").replace("'", "'\\''") + "'" for x in pieces), encoding="utf-8")
    target = Path(args.output).resolve() if args.output else root / ("film-" + export_id + ".mp4")
    if target.exists():
        raise FilmError(f"Refusing to overwrite export: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    run_process([cfg["ffmpeg"], "-v", "error", "-f", "concat", "-safe", "0", "-i", listing, "-c", "copy", "-movflags", "+faststart", target])
    run_process([cfg["ffmpeg"], "-v", "error", "-i", target, "-f", "null", "-"])
    info = probe(cfg, target)
    p["exports"].append({"file": str(target), "media": info, "created": time.time(), "segments": len(segments)})
    save(root, p)
    return {"status": "exported", "file": str(target), "media": info, "segments": len(segments)}


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ["init", "add", "import", "run", "wait", "status", "accept", "reject", "recover", "extract", "inspect", "doctor", "start", "trim", "join", "stitch", "unlock", "loras", "preview"]:
        a = sub.add_parser(name)
        a.add_argument("--project", required=True)
        if name in ["run", "wait", "status", "accept", "reject", "recover", "extract", "inspect", "trim"]:
            a.add_argument("--segment", type=int)
        if name == "init":
            a.add_argument("--title")
            a.add_argument("--workflow")
            a.add_argument("--bindings")
            a.add_argument("--server")
            a.add_argument("--ffmpeg")
            a.add_argument("--ffprobe")
            a.add_argument("--width", type=int, default=768)
            a.add_argument("--height", type=int, default=1344)
            a.add_argument("--fps", type=int, default=24)
            a.add_argument("--quality", choices=["turbo", "standard", "workflow"], default="turbo")
            a.add_argument("--audio", choices=["generated", "silent"], default="generated")
            a.add_argument("--music", choices=["none", "generated", "later"], default="none")
            a.add_argument("--seconds", type=float, default=10)
        if name == "add":
            a.add_argument("--text-only", action="store_true", help="generate from text without keyframes")
            a.add_argument("--first")
            a.add_argument("--last")
            a.add_argument("--loop", action="store_true")
            a.add_argument("--guide", nargs="?", const="prev",
                           help="continue an existing clip: 'prev' (default) for the accepted previous segment, or a path")
            a.add_argument("--guide-frames", type=int, default=22)
            a.add_argument("--ref2va", action="append", metavar="IMAGE",
                           help="reference picture for Ref2VA (repeatable, 1-9); combines with --first/--last/--guide")
            a.add_argument("--ref2va-model", metavar="UNET",
                           help="diffusion model for Ref2VA (default: the project's own model)")
            a.add_argument("--ref2va-lora", metavar="LORA", help="speed LoRA for Ref2VA, e.g. the 4-step ref2v turbo")
            a.add_argument("--ref2va-steps", type=int, default=20)
            a.add_argument("--ref2va-size", choices=["match", "max"], default="match",
                           help="'max' keeps reference detail at any cost, 'match' fits them to the canvas")
            a.add_argument("--prompt-file", required=True)
            a.add_argument("--seconds", type=float)
        if name == "import":
            a.add_argument("--file", required=True)
            a.add_argument("--replace-rejected", action="store_true", help="replace only the latest rejected candidate, preserving history")
        if name == "run":
            a.add_argument("--prompt-file")
            a.add_argument("--first", help="revise a rejected/draft clip to start a new action from this still instead of its motion guide")
            a.add_argument("--seconds", type=float)
            a.add_argument("--seed", type=int)
            a.add_argument("--enqueue", action="store_true")
            a.add_argument("--lora", action="append", metavar="NAME",
                           help="adapter/LoRA from ComfyUI's loras dir (repeatable); a path is reduced to its filename")
            a.add_argument("--lora-strength", type=float, default=None,
                           help="strength applied to every --lora (default 1.0)")
            a.add_argument("--no-lora", action="store_true",
                           help="run without the adapters recorded on this segment")
        if name == "wait":
            a.add_argument("--timeout", type=float, default=7200)
            a.add_argument("--poll", type=float, default=5)
        if name == "reject":
            a.add_argument("--reason", required=True)
        if name == "extract":
            a.add_argument("--which", choices=["first", "last"], default="last")
            a.add_argument("--scale", type=int, choices=[1, 2, 3, 4], default=2)
        if name == "trim":
            a.add_argument("--head", type=float, default=0)
            a.add_argument("--tail", type=float, default=0)
        if name == "join":
            a.add_argument("--after", type=int, required=True)
            a.add_argument("--mode", choices=["cut", "crossfade", "optical"], default="cut")
            a.add_argument("--seconds", type=float, default=.25)
        if name == "preview":
            a.add_argument("--name", help="previz project folder name (default: '<project> previz WxH')")
            a.add_argument("--width", type=int, help="preview width, multiple of 32 (default 384)")
            a.add_argument("--height", type=int, help="preview height, multiple of 32 (default 672)")
            a.add_argument("--seconds", type=float, help="default preview take length (default 5)")
        if name == "stitch":
            a.add_argument("--output")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.command == "init":
        return init_project(args)
    if args.command == "unlock":
        path = Path(args.project).resolve() / ".pipeline" / "lock"
        if path.exists():
            pid = int(path.read_text())
            if os.name == "nt":
                import ctypes
                handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
                if handle:
                    ctypes.windll.kernel32.CloseHandle(handle)
                    raise FilmError(f"Lock owner PID {pid} still exists; not unlocked")
            else:
                try:
                    os.kill(pid, 0)
                except ProcessLookupError:
                    pass
                else:
                    raise FilmError(f"Lock owner PID {pid} still exists")
            path.unlink()
        return {"status": "unlocked"}
    if args.command == "wait":
        if args.poll <= 0 or args.timeout <= 0:
            raise FilmError("poll and timeout must be positive")
        return wait_for(args)
    with project_lock(args.project):
        root, p = load_project(args.project)
        if args.command in ["add", "import"]:
            return add_segment(args, root, p)
        if args.command == "status":
            return summary(root, p, segment(p, args.segment) if args.segment else None)
        if args.command == "doctor":
            return doctor(root, p)
        if args.command == "start":
            return ensure_server(p["config"])
        if args.command == "run":
            return submit(args, root, p)
        if args.command == "preview":
            return preview_project(args, root, p)
        if args.command == "loras":
            return {"server": p["config"]["server"], "loras": server_loras(p["config"])}
        if args.command == "accept":
            return accept(args, root, p)
        if args.command == "recover":
            return recover(root, p, segment(p, args.segment))
        if args.command == "extract":
            return extract(args, root, p)
        if args.command == "inspect":
            return inspect_segment(args, root, p)
        if args.command == "reject":
            s = segment(p, args.segment)
            if s["status"] != "review":
                raise FilmError("Only a review candidate can be rejected")
            s.update(status="rejected", rejection=args.reason)
        elif args.command == "trim":
            s = segment(p, args.segment)
            if s["status"] != "accepted" or min(args.head, args.tail) < 0:
                raise FilmError("Nonnegative trims require an accepted segment")
            if args.head + args.tail >= s["media"]["duration"] - 1 / p["config"]["fps"]:
                raise FilmError("Trims consume the segment")
            s.update(trim_head=args.head, trim_tail=args.tail)
        elif args.command == "join":
            if not 1 <= args.after < len(p["segments"]) or not 0 < args.seconds <= 2:
                raise FilmError("Choose an existing boundary and a transition of 0–2 seconds")
            p["joins"][str(args.after)] = {"mode": args.mode, "seconds": 0 if args.mode == "cut" else args.seconds}
        elif args.command == "stitch":
            return stitch(args, root, p)
        save(root, p)
        return summary(root, p)


if __name__ == "__main__":
    try:
        emit(main())
    except (FilmError, OSError, ValueError, KeyError) as e:
        emit({"error": str(e), "automatic_retry": False})
        sys.exit(1)
