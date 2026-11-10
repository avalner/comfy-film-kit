"""Interpolate a clip with RIFE in ComfyUI, optionally retime it.

Solves the frame-duplication problem of the plain ffmpeg speed-up: interpolate to
48 fps, then sample that at 1.3x. A 24 fps source sped up 1.3x needs 31.2 fps of
content; a 48 fps source provides ~36.9 fps after the speed-up, so the 24 fps
result is built from real intermediate frames.

Usage:
    python rife.py --input CLIP.mp4 --speed 1.3 --out RESULT.mp4
    python rife.py --input CLIP.mp4 --multiplier 4 --out SLOW_INTERMEDIATE.mp4

Prints one compact JSON object. Requires a running ComfyUI with
ComfyUI-Frame-Interpolation and VideoHelperSuite installed.
"""
import argparse
import json
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORKFLOW = HERE.parent / "assets" / "workflows" / "rife-2x.json"
SERVER = "http://127.0.0.1:8188"
COMFY_OUTPUT = Path("I:/Video Generation/ComfyUI_windows_portable/ComfyUI/output")
FFMPEG = "C:/Program Files/Shotcut/ffmpeg.exe"
FFPROBE = "C:/Program Files/Shotcut/ffprobe.exe"


def api(path, payload=None, timeout=60):
    url = SERVER + path
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=timeout))


def interpolate(src: Path, multiplier: int, prefix: str, timeout_s: int):
    graph = json.loads(WORKFLOW.read_text(encoding="utf-8"))
    # ComfyUI treats every top-level key as a node id; drop documentation keys.
    graph = {k: v for k, v in graph.items() if not k.startswith("_")}
    graph["1"]["inputs"]["video"] = str(src)
    graph["2"]["inputs"]["multiplier"] = multiplier
    graph["3"]["inputs"]["frame_rate"] = 24 * multiplier
    graph["3"]["inputs"]["filename_prefix"] = prefix
    prompt_id = api("/prompt", {"prompt": graph, "client_id": "rife-" + uuid.uuid4().hex[:8]})["prompt_id"]

    deadline = time.time() + timeout_s
    while time.time() < deadline:
        time.sleep(3)
        entry = api(f"/history/{prompt_id}", timeout=30).get(prompt_id)
        if not entry:
            continue
        status = entry.get("status", {})
        if status.get("status_str") == "error":
            raise RuntimeError(json.dumps(status)[:1500])
        if status.get("completed"):
            items = []
            for node in entry.get("outputs", {}).values():
                for key in ("gifs", "videos"):
                    items += node.get(key, [])
            if not items:
                raise RuntimeError("Interpolation finished but no video output was reported")
            item = items[0]
            path = item.get("fullpath") or str(COMFY_OUTPUT / item.get("subfolder", "") / item["filename"])
            return path, item.get("metadata", {})
    raise RuntimeError("Timed out waiting for the RIFE job")


def speed_up(src: Path, dst: Path, factor: float):
    subprocess.run([
        FFMPEG, "-v", "error", "-y", "-i", str(src),
        "-filter_complex",
        f"[0:v]setpts=PTS/{factor},fps=24[v];[0:a]atempo={factor}[a]",
        "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-crf", "17", "-preset", "fast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(dst),
    ], check=True)
    probe = json.loads(subprocess.run([
        FFPROBE, "-v", "error", "-show_entries", "format=duration",
        "-show_entries", "stream=nb_frames,r_frame_rate", "-of", "json", str(dst),
    ], capture_output=True, check=True).stdout)
    return probe


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--multiplier", type=int, default=2)
    ap.add_argument("--prefix", default="rife_test/clip")
    ap.add_argument("--speed", type=float, help="retime factor, e.g. 1.3 for a 30%% speed-up")
    ap.add_argument("--out", help="final path when --speed is used")
    ap.add_argument("--timeout", type=int, default=1800)
    args = ap.parse_args()

    src = Path(args.input).resolve()
    interpolated, meta = interpolate(src, args.multiplier, args.prefix, args.timeout)
    result = {"interpolated": interpolated, "metadata": meta}

    if args.speed:
        dst = Path(args.out).resolve() if args.out else src.with_name(src.stem + f"-x{args.speed}.mp4")
        if dst.exists():
            raise SystemExit(f"Refusing to overwrite {dst}")
        result["probe"] = speed_up(Path(interpolated), dst, args.speed)
        result["output"] = str(dst)

    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
