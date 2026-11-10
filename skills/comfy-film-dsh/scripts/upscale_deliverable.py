"""Delivery upscale: Real-ESRGAN x2 over the accepted final film, audio copied, decode verified.

Frames are upscaled by the ncnn Vulkan build (fast batch, no VRAM limits), then re-encoded at 24 fps
with the original soundtrack and +faststart. The source file is never modified.
"""
import argparse, hashlib, json, os, shutil, subprocess, sys, tempfile, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_EXE = Path(r"I:\Video Generation\Tools\realesrgan\realesrgan-ncnn-vulkan.exe")
DEFAULT_MODELS = Path(r"I:\Video Generation\Tools\realesrgan\models")
FFMPEG = Path(r"C:/Program Files/Shotcut/ffmpeg.exe")
FFPROBE = Path(r"C:/Program Files/Shotcut/ffprobe.exe")


def run(cmd, **kw):
    return subprocess.run([str(c) for c in cmd], check=True, capture_output=True, text=True, **kw)


def probe(path):
    out = run([FFPROBE, "-v", "error", "-select_streams", "v:0", "-count_frames",
               "-show_entries", "stream=width,height,r_frame_rate,nb_read_frames",
               "-show_entries", "format=duration", "-of", "json", path]).stdout
    d = json.loads(out)
    s = d["streams"][0]
    num, den = s["r_frame_rate"].split("/")
    return {"width": s["width"], "height": s["height"], "fps": float(num) / float(den),
            "frames": int(s["nb_read_frames"]), "duration": float(d["format"]["duration"])}


def has_audio(path):
    out = run([FFPROBE, "-v", "error", "-select_streams", "a", "-show_entries", "stream=index",
               "-of", "csv=p=0", path]).stdout.strip()
    return bool(out)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--output")
    ap.add_argument("--scale", type=int, default=2)
    ap.add_argument("--model", default="realesr-animevideov3")
    ap.add_argument("--crf", type=int, default=16)
    ap.add_argument("--preset", default="medium")
    ap.add_argument("--exe", default=str(DEFAULT_EXE))
    ap.add_argument("--model-dir", default=str(DEFAULT_MODELS))
    ap.add_argument("--keep-temp", action="store_true")
    a = ap.parse_args()

    src = Path(a.input).resolve()
    if not src.is_file():
        raise SystemExit(f"missing input: {src}")
    out = Path(a.output).resolve() if a.output else src.with_name(src.stem + f"-{a.scale}x.mp4")
    if out.exists():
        raise SystemExit(f"refusing to overwrite {out}")
    info = probe(src)

    work = Path(tempfile.mkdtemp(prefix="upscale-", dir=src.parent / ".pipeline"))
    frames_in, frames_out = work / "in", work / "out"
    frames_in.mkdir(); frames_out.mkdir()
    t0 = time.time()
    run([FFMPEG, "-v", "error", "-i", src, "-start_number", "0", "-frames:v", str(info["frames"]),
         str(frames_in / "%06d.png")])
    n = len(list(frames_in.glob("*.png")))
    run([a.exe, "-i", str(frames_in), "-o", str(frames_out), "-n", a.model,
         "-s", str(a.scale), "-m", a.model_dir, "-f", "png"])
    m = len(list(frames_out.glob("*.png")))
    if n != m:
        raise SystemExit(f"upscaler produced {m} of {n} frames")
    upscale_seconds = time.time() - t0

    cmd = [FFMPEG, "-v", "error", "-y", "-framerate", str(info["fps"]),
           "-start_number", "0", "-i", str(frames_out / "%06d.png")]
    audio = has_audio(src)
    if audio:
        cmd += ["-i", str(src), "-map", "0:v:0", "-map", "1:a:0", "-c:a", "copy"]
    cmd += ["-frames:v", str(n), "-c:v", "libx264", "-preset", a.preset, "-crf", str(a.crf),
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out)]
    run(cmd)

    up = probe(out)
    run([FFMPEG, "-v", "error", "-i", out, "-f", "null", "-"])
    result = {
        "input": str(src), "output": str(out),
        "source": info, "upscaled": up, "scale": a.scale, "model": a.model,
        "frames_upscaled": m, "upscale_seconds": round(upscale_seconds, 1),
        "size_mb": round(out.stat().st_size / 1e6, 1), "sha256": sha256(out),
        "audio": audio, "decode": "passed",
    }
    if not a.keep_temp:
        shutil.rmtree(work, ignore_errors=True)
    print(json.dumps(result))


if __name__ == "__main__":
    sys.exit(main())
