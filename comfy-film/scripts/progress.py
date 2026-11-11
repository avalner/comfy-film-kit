"""Read-only local progress panel. No generation, cancellation or model calls."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import shutil
import signal
import sys
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = Path(__file__).resolve().parent

# The panel is English unless the conversation is Russian. Precedence:
# explicit --lang, then COMFY_FILM_LANG in the environment, then English.
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


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def snapshot(root, lang="en"):
    film = read(root / "film.json")
    segments = film.get("segments", [])
    s = next((s for s in segments if s["status"] in ("running", "submitting")), segments[-1] if segments else {})
    attempt = (s.get("attempts") or [{}])[-1]
    result = dict(title=film["title"], segment=s.get("number"), status=s.get("status", "draft"),
                  lang=lang, server=film["config"]["server"], generator=film["bindings"]["generator"],
                  prompt=attempt.get("prompt_id"), client=attempt.get("client_id"), labels={})
    graph_path = root / ".pipeline" / "workflow-api.json"
    if graph_path.exists():
        result["labels"] = {k: v.get("class_type", k) for k, v in read(graph_path).items()}
    result["samplers"] = [k for k, label in result["labels"].items() if "sampler" in label.lower() and "select" not in label.lower()]
    try:
        live = read(root / ".pipeline" / "progress-live.json")
        if live.get("prompt") == result["prompt"]:
            result["live"] = live
            if time.time() - live.get("updated", 0) > 10:
                result["live"]["connected"] = False
    except (OSError, ValueError):
        pass
    if result["status"] == "running" and result["prompt"]:
        try:
            with urllib.request.urlopen(result["server"].rstrip("/") + "/history/" + result["prompt"], timeout=2) as response:
                entry = json.load(response).get(result["prompt"], {})
            status = entry.get("status", {})
            if status.get("status_str") == "error":
                result["status"] = "failed"
            elif status.get("completed"):
                result["status"] = "review"
        except Exception:
            result["connection_warning"] = True  # the page renders the localised text
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
                elif route in ("/", "/progress.js"):
                    name = "progress.html" if route == "/" else "progress.js"
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
    node = shutil.which("node")
    if node:
        subprocess.Popen([node, str(HERE / "progress-worker.cjs"), str(root), str(os.getpid())],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    info = {"url": f"http://127.0.0.1:{server.server_port}", "pid": os.getpid(), "lang": lang}
    path = root / ".pipeline" / "progress-server.json"
    path.parent.mkdir(exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(info), encoding="utf-8")
    os.replace(tmp, path)
    server.serve_forever()


def launch(root, lang=None):
    lang = resolve_lang(lang)
    record = root / ".pipeline" / "progress-server.json"

    def existing():
        try:
            info = read(record)
            # Only contact this helper's local loopback endpoint.
            from urllib.parse import urlsplit
            url = urlsplit(info["url"])
            if url.scheme != "http" or url.hostname != "127.0.0.1":
                return None
            with urllib.request.urlopen(info["url"] + "/health", timeout=1) as response:
                if json.load(response).get("project") == str(root):
                    return info
        except Exception:
            pass
        return None

    if info := existing():
        if info.get("lang") == lang:
            return info
        # A panel left over from a conversation in another language: it holds no state,
        # so restart it rather than showing the wrong language next to a render.
        try:
            os.kill(info["pid"], signal.SIGTERM)
            time.sleep(0.4)
        except Exception:
            pass
    flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    subprocess.Popen([sys.executable, str(HERE / "progress.py"), "--project", str(root), "--serve",
                      "--lang", lang],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     creationflags=flags, close_fds=True)
    for _ in range(40):
        time.sleep(.2)
        if info := existing():
            return info
    raise RuntimeError("Progress panel failed to start")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--lang", choices=LANGS, default=None,
                        help=f"panel language (default: ${LANG_ENV} or en)")
    args = parser.parse_args()
    root = Path(args.project).resolve()
    read(root / "film.json")
    lang = resolve_lang(args.lang)
    if args.serve:
        serve(root, lang)
    else:
        print(json.dumps(launch(root, lang)))
