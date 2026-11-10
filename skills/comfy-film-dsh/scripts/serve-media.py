"""Static file server for reviewing rendered video in the DSH sidebar.

Two problems with `python -m http.server` and with serving the .mp4 directly:

1. SimpleHTTPRequestHandler ignores the HTTP Range header. Browsers always
   request video with `Range: bytes=0-`, so the default handler answers 200
   with the whole file, the player cannot seek, and it aborts on every scrub
   -> ConnectionResetError tracebacks.
2. DSH's embedded Browser reports `did-fail-load` when a navigation goes
   straight to a media file: Chromium cancels the document load and commits a
   media viewer instead, so the user sees the red banner "The page could not
   load; reload or open it in the system browser." once per tab, even though
   the stream is fine. Navigating to an HTML page avoids it entirely.

So: `/watch/<path>` returns a tiny player page, `/ <path>` returns the file
with 206 Partial Content support. Client aborts are swallowed quietly.

Usage:
    python serve-media.py --directory "I:\\Video Generation" --port 8199
    python serve-media.py                       # defaults: cwd, port 8199
"""

from __future__ import annotations

import argparse
import html
import mimetypes
import os
import re
import sys
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$")

# Errors Windows raises when the browser or video player drops the socket.
# They are routine for a scrubbing player, so they must not print tracebacks.
CLIENT_GONE = (BrokenPipeError, ConnectionResetError, ConnectionAbortedError)

EXTRA_TYPES = {
    ".mp4": "video/mp4",
    ".m4v": "video/mp4",
    ".webm": "video/webm",
    ".mov": "video/quicktime",
    ".mkv": "video/x-matroska",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
}

AUDIO_EXT = {".mp3", ".wav", ".m4a", ".ogg", ".flac"}

WATCH_PREFIX = "/watch/"

PAGE = """<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  html, body {{ margin: 0; height: 100%; background: #0b0b0c; color: #d8d8da; }}
  body {{ display: flex; flex-direction: column; font: 12px/1.4 "Segoe UI", sans-serif; }}
  main {{ flex: 1; display: flex; align-items: center; justify-content: center; padding: 8px; min-height: 0; }}
  video {{ max-width: 100%; max-height: 100%; background: #000; outline: none; }}
  footer {{ display: flex; gap: 12px; align-items: center; padding: 6px 10px; background: #141416; }}
  footer span {{ overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
  footer a {{ color: #7aa7ff; text-decoration: none; margin-left: auto; white-space: nowrap; }}
</style>
</head>
<body>
<main><video controls autoplay {extra} src="{src}"></video></main>
<footer><span>{name}</span><a href="{raw}">файл напрямую</a></footer>
</body>
</html>
"""


def guess_type(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext in EXTRA_TYPES:
        return EXTRA_TYPES[ext]
    return mimetypes.guess_type(path)[0] or "application/octet-stream"


class Handler(BaseHTTPRequestHandler):
    server_version = "serve-media/1.1"
    protocol_version = "HTTP/1.1"

    # ---- plumbing -------------------------------------------------------
    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        status = getattr(self, "_status", "-")
        span = getattr(self, "_span", "")
        sys.stdout.write(f"{status} {self.command} {self.path}{span}\n")
        sys.stdout.flush()

    def log_error(self, fmt: str, *args) -> None:  # noqa: A003
        # send_error() logs the code itself, then calls log_error; printing
        # both yields a stray "- GET ..." line above every 404.
        pass

    def send_response(self, code, message=None) -> None:  # noqa: ANN001
        self._status = int(code)
        super().send_response(code, message)

    def split_path(self) -> tuple[str, str] | None:
        parts = urllib.parse.urlsplit(self.path)
        raw = urllib.parse.unquote(parts.path)
        return raw, parts.query

    def resolve(self, url_path: str) -> str | None:
        base = url_path
        if base.startswith(WATCH_PREFIX):
            base = base[len(WATCH_PREFIX) - 1 :]
        bits = [p for p in base.split("/") if p and p not in (".", "..")]
        target = os.path.join(self.server.root, *bits)  # type: ignore[attr-defined]
        return os.path.normpath(target)

    def send_payload(self, data: bytes, ctype: str, head_only: bool) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if not head_only:
            try:
                self.wfile.write(data)
            except CLIENT_GONE:
                pass

    # ---- verbs ----------------------------------------------------------
    def do_HEAD(self) -> None:  # noqa: N802
        self.respond(body=False)

    def do_GET(self) -> None:  # noqa: N802
        self.respond(body=True)

    def respond(self, body: bool) -> None:
        split = self.split_path()
        if split is None:
            self.send_error(HTTPStatus.BAD_REQUEST)
            return
        url_path, query = split

        if url_path.startswith(WATCH_PREFIX):
            self.serve_player(url_path, query, body)
            return

        target = self.resolve(url_path)
        if target is None or not os.path.isfile(target):
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        self.serve_file(target, body)

    def serve_player(self, url_path: str, query: str, body: bool) -> None:
        target = self.resolve(url_path)
        if target is None or not os.path.isfile(target):
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        rel = "/" + url_path[len(WATCH_PREFIX) :].lstrip("/")
        src = urllib.parse.quote(rel, safe="/")
        if query:
            src = f"{src}?{urllib.parse.quote(query, safe='=&%')}"

        name = os.path.basename(target)
        ext = os.path.splitext(name)[1].lower()
        extra = 'type="audio/x-wav"' if ext in AUDIO_EXT else ""
        page = PAGE.format(
            title=html.escape(name),
            name=html.escape(name),
            src=html.escape(src, quote=True),
            raw=html.escape(src, quote=True),
            extra=extra,
        ).encode("utf-8")
        self.send_payload(page, "text/html; charset=utf-8", head_only=not body)

    def serve_file(self, target: str, body: bool) -> None:
        size = os.path.getsize(target)
        ctype = guess_type(target)
        span = self.parse_range(size)

        if span is None:  # unsatisfiable range
            self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
            self.send_header("Content-Range", f"bytes */{size}")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        start, end = span
        length = end - start + 1
        partial = (start, end) != (0, size - 1)

        self.send_response(HTTPStatus.PARTIAL_CONTENT if partial else HTTPStatus.OK)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        if partial:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self._span = f"  [{start}-{end}/{size}]"
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if not body:
            return

        try:
            with open(target, "rb") as fh:
                fh.seek(start)
                remaining = length
                while remaining > 0:
                    chunk = fh.read(min(256 * 1024, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
        except CLIENT_GONE:
            # Player closed the socket: normal when the user scrubs or closes
            # the preview. Not an error worth a traceback.
            pass

    def parse_range(self, size: int) -> tuple[int, int] | None:
        header = self.headers.get("Range")
        if not header:
            return (0, size - 1)
        match = RANGE_RE.match(header.strip())
        if not match:
            return (0, size - 1)
        first, last = match.group(1), match.group(2)
        if not first:  # suffix form: bytes=-500
            if not last:
                return (0, size - 1)
            n = int(last)
            return (max(size - n, 0), size - 1)
        start = int(first)
        end = int(last) if last else size - 1
        end = min(end, size - 1)
        if start > end or start >= size:
            return None
        return (start, end)


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, addr: tuple[str, int], root: str) -> None:
        self.root = root
        super().__init__(addr, Handler)

    def handle_error(self, request, client_address) -> None:  # noqa: ANN001
        # Windows raises these while a player is dropping the connection;
        # everything else is worth a traceback.
        if isinstance(sys.exc_info()[1], CLIENT_GONE):
            return
        super().handle_error(request, client_address)

    def shutdown_request(self, request) -> None:  # noqa: ANN001
        try:
            super().shutdown_request(request)
        except CLIENT_GONE:
            pass


def main() -> int:
    ap = argparse.ArgumentParser(description="Range-capable media server.")
    ap.add_argument("--directory", default=os.getcwd())
    ap.add_argument("--port", type=int, default=8199)
    ap.add_argument("--bind", default="127.0.0.1")
    args = ap.parse_args()

    root = os.path.abspath(args.directory)
    if not os.path.isdir(root):
        print(f"not a directory: {root}", file=sys.stderr)
        return 2

    srv = Server((args.bind, args.port), root)
    print(f"root: {root}", flush=True)
    print(f"url:  http://{args.bind}:{args.port}/watch/", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
