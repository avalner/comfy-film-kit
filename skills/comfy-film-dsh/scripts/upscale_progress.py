"""Read-only progress panel for the SeedVR2 delivery upscale.

Mirrors the behaviour and the look of the generation panel (progress.py) but reports the
upscale instead: it finds the newest seedvr2-* work directory in the project's .pipeline,
parses the SeedVR2 log the helper already writes, and reports the chunk/phase/batch position.

It never starts, cancels or modifies an upscale; it only reads files.

The panel is English by default; pass --lang ru (or set COMFY_FILM_LANG=ru) when the
conversation with the user is Russian.

    python upscale_progress.py --project PROJECT --serve [--lang ru]
    python upscale_progress.py --project PROJECT          # one-shot JSON snapshot
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent

# English unless the conversation is Russian. Precedence: --lang, COMFY_FILM_LANG, en.
LANG_ENV = "COMFY_FILM_LANG"
LANGS = ("en", "ru")


def resolve_lang(value=None):
    """Normalise a language tag to a supported panel language (default English)."""
    for candidate in (value, os.environ.get(LANG_ENV)):
        if candidate:
            tag = str(candidate).strip().lower().replace("_", "-")[:2]
            if tag in LANGS:
                return tag
    return "en"


# Measured share of a chunk's wall time, used when pacing the sub-chunk estimate.
PHASE_NAMES = {
    "en": {
        1: "VAE encoding",
        2: "DiT upscale",
        3: "VAE decoding",
        4: "Post-processing",
    },
    "ru": {
        1: "VAE-кодирование",
        2: "DiT-апскейл",
        3: "VAE-декодирование",
        4: "Пост-обработка",
    },
}
FINISHED = {"en": "Done", "ru": "Готово"}
# Relative weights observed in production (encode, upscale, decode, post).
PHASE_WEIGHTS = {1: 60, 2: 60, 3: 130, 4: 13}
CHUNK_SECONDS = sum(PHASE_WEIGHTS.values())

RE_CHUNK = re.compile(r"Chunk (\d+)/(\d+):")
RE_PHASE = re.compile(r"Phase (\d):")
RE_BATCH = re.compile(r"(Encoding|Decoding) batch (\d+)/(\d+)")
RE_UPSCALING = re.compile(r"Upscaling batch (\d+)/(\d+)")
RE_STAMP = re.compile(r"^\[(\d\d):(\d\d):(\d\d)\.\d+\]")


def newest_workdir(root):
    base = root / ".pipeline"
    if not base.is_dir():
        return None
    dirs = [d for d in base.iterdir() if d.is_dir() and d.name.startswith("seedvr2-")]
    return max(dirs, key=lambda d: d.stat().st_mtime) if dirs else None


def parse_log(path, out_path, lang="en"):
    """Return the upscale position. Frames on disk are the authoritative done-count."""
    phases = PHASE_NAMES.get(lang, PHASE_NAMES["en"])
    data = {
        "active": True,
        "chunk": None,
        "chunks": None,
        "phase": None,
        "phase_name": None,
        "batch": None,
        "batches": None,
        "frames_done": 0,
        "frames_total": None,
        "last_line": "",
        "stamp": None,
    }
    if not path.is_file():
        return data
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    for line in lines:
        if m := RE_CHUNK.search(line):
            data["chunk"], data["chunks"] = int(m.group(1)), int(m.group(2))
        if m := RE_PHASE.search(line):
            data["phase"] = int(m.group(1))
            data["phase_name"] = phases.get(data["phase"], f"Phase {data['phase']}")
            data["batch"] = data["batches"] = None
        if m := RE_BATCH.search(line):
            data["batch"], data["batches"] = int(m.group(2)), int(m.group(3))
        if m := RE_UPSCALING.search(line):
            data["batch"], data["batches"] = int(m.group(1)), int(m.group(2))
        if stamp := RE_STAMP.match(line):
            h, mi, s = (int(x) for x in stamp.groups())
            data["stamp"] = h * 3600 + mi * 60 + s
        if line.strip():
            data["last_line"] = line.strip()

    frames_dir = path.parent / "frames"
    if frames_dir.is_dir():
        data["frames_done"] = sum(1 for _ in frames_dir.rglob("*.png"))

    # Total frames: read from the source probe if the finished file is not there yet.
    if out_path and out_path.is_file():
        data["active"] = False
        data["finished"] = True
    return data


def probe_frames(src):
    try:
        from upscale_deliverable import probe
        return probe(Path(src))["frames"]
    except Exception:
        return None


def snapshot(root, lang="en"):
    work = newest_workdir(root)
    result = {"project": str(root), "kind": "upscale", "lang": lang, "work": str(work) if work else None}

    # The helper removes its work directory on success, so a missing log must not be read as
    # "nothing happened": fall back to the delivered file pair and report completion.
    source = None
    out_path = None
    sources = [p for p in root.glob("*-final-v*.mp4") if not p.stem.endswith("-2x")]
    if sources:
        source = max(sources, key=lambda p: p.stat().st_mtime)
        out_path = source.with_name(source.stem + "-2x.mp4")

    if work is None:
        if out_path and out_path.is_file():
            total = probe_frames(source) if source else None
            result.update(
                active=False,
                exists=True,
                finished=True,
                percent=100.0,
                frames_done=total,
                frames_total=total,
                phase_name=FINISHED.get(lang, FINISHED["en"]),
                source=str(source),
                output=str(out_path),
            )
        else:
            result.update(active=False, exists=False)
        return result
    log = work / "seedvr2.log"

    data = parse_log(log, out_path, lang)
    total = probe_frames(source) if source else None

    # Percentage: whole chunks plus the fraction of the running chunk.
    pct = None
    if data["chunks"] and data["chunk"]:
        done_chunks = data["chunk"] - 1
        phase_frac = 0.0
        if data["phase"] in PHASE_WEIGHTS:
            before = sum(w for p, w in PHASE_WEIGHTS.items() if p < data["phase"])
            inner = 0.0
            if data["phase"] in (1, 2, 3) and data["batches"]:
                inner = (data["batch"] or 0) / data["batches"]
            phase_frac = (before + PHASE_WEIGHTS[data["phase"]] * inner) / CHUNK_SECONDS
        pct = round(100.0 * (done_chunks + phase_frac) / data["chunks"], 1)

    finished = bool(out_path and out_path.is_file())
    result.update(
        active=not finished,
        exists=True,
        chunk=data["chunk"],
        chunks=data["chunks"],
        phase=data["phase"],
        phase_name=data["phase_name"],
        batch=data["batch"],
        batches=data["batches"],
        frames_done=data["frames_done"],
        frames_total=total,
        percent=100.0 if finished else pct,
        last_line=data["last_line"],
        log=str(log),
        source=str(source) if source else None,
    )
    if finished:
        result["output"] = str(out_path)
    return result


def serve(root, lang="en"):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            try:
                route = self.path.split("?", 1)[0]
                if route == "/health":
                    data, mime = json.dumps({"project": str(root)}).encode(), "application/json"
                elif route == "/api":
                    data, mime = json.dumps(snapshot(root, lang), ensure_ascii=False).encode(), "application/json"
                elif route in ("/", "/upscale-progress.js"):
                    name = "upscale-progress.html" if route == "/" else "upscale-progress.js"
                    data = (HERE / name).read_bytes()
                    if route == "/":
                        data = data.replace(b"__LANG__", lang.encode("ascii", "ignore"))
                    mime = "text/html" if route == "/" else "text/javascript"
                else:
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header("Content-Type", mime + "; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception:
                self.send_error(503, "Progress temporarily unavailable")

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    info = {"url": f"http://127.0.0.1:{server.server_port}", "pid": os.getpid()}
    path = root / ".pipeline" / "upscale-progress-server.json"
    path.parent.mkdir(exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(info), encoding="utf-8")
    tmp.replace(path)
    server.serve_forever()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--project", required=True)
    ap.add_argument("--serve", action="store_true")
    ap.add_argument("--lang", choices=LANGS, default=None,
                    help=f"panel language (default: ${LANG_ENV} or en)")
    a = ap.parse_args()
    root = Path(a.project).resolve()
    lang = resolve_lang(a.lang)
    if a.serve:
        serve(root, lang)
    else:
        print(json.dumps(snapshot(root, lang), ensure_ascii=False, indent=2))
