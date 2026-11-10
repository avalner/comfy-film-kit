"""Measure motion over a clip to catch dead beats and end-of-clip freezes.

FL2VA always eases into its last frame, so every generated clip ends almost
still; a prompt can also produce a "preparation" that the model renders as
standing in place. Both look like a frozen video to the viewer. This prints the
per-window motion so the freeze is found before the take is shown for review.

Usage:
    python motion_profile.py CLIP.mp4 [--window 0.5] [--dead 0.5] [--still 1.2]
                             [--ffmpeg PATH] [--ffprobe PATH]

Two levels:
- dead  (default < 0.5) — the frame barely changes: a frozen shot.
- still (default < 1.2) — small residual motion (antennae, breathing): a held beat.

verdict "dead" when a dead run lasts at least 1.0 s or sits strictly inside the
clip. A dead *tail* shorter than 1 s is normal for FL2VA; trim it anyway when
the shot is supposed to keep moving, and never show a take with a 1 s hold
without deciding about it. A dead run in the middle means the beat did not
happen: re-prompt with silhouette-changing action instead of re-rolling.

Decoding uses ffmpeg to raw gray frames, so no cv2 is needed — the bundled
interpreter from assets/machine.json is enough.
"""
import argparse
import json
import subprocess
import sys

import numpy as np


def probe(ffprobe, path):
    out = subprocess.check_output([
        ffprobe, "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height,r_frame_rate",
        "-of", "json", path,
    ])
    stream = json.loads(out)["streams"][0]
    num, den = stream["r_frame_rate"].split("/")
    return float(num) / float(den)


def frames(ffmpeg, path, width, height):
    cmd = [ffmpeg, "-v", "error", "-i", path, "-vf", f"scale={width}:{height},format=gray",
           "-f", "rawvideo", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    size = width * height
    try:
        while True:
            buf = proc.stdout.read(size)
            if len(buf) < size:
                break
            yield np.frombuffer(buf, dtype=np.uint8)
    finally:
        proc.stdout.close()
        err = proc.stderr.read().decode("utf-8", "replace").strip()
        proc.wait()
        if proc.returncode not in (0, None) and err:
            sys.stderr.write(err + "\n")


def runs_below(windows, limit, win):
    runs = []
    for i, w in enumerate(windows):
        if w["mean"] < limit:
            if runs and runs[-1]["i1"] == i - 1:
                runs[-1]["end"] = round(w["t"] + win, 2)
                runs[-1]["i1"] = i
            else:
                runs.append({"start": w["t"], "end": round(w["t"] + win, 2), "i0": i, "i1": i})
    for r in runs:
        r["seconds"] = round(r["end"] - r["start"], 2)
    return runs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("clip")
    ap.add_argument("--window", type=float, default=0.5)
    ap.add_argument("--dead", type=float, default=0.5)
    ap.add_argument("--still", type=float, default=1.2)
    ap.add_argument("--ffmpeg", default="C:/Program Files/Shotcut/ffmpeg.exe")
    ap.add_argument("--ffprobe", default="C:/Program Files/Shotcut/ffprobe.exe")
    ap.add_argument("--scale", default="152x264", help="WxH the frames are reduced to before diffing")
    args = ap.parse_args()

    w, h = (int(v) for v in args.scale.lower().replace(":", "x").split("x"))
    fps = probe(args.ffprobe, args.clip)

    diffs = []
    prev = None
    for frame in frames(args.ffmpeg, args.clip, w, h):
        if prev is not None:
            diffs.append(float(np.abs(frame.astype(np.int16) - prev.astype(np.int16)).mean()))
        prev = frame

    per = max(1, int(round(args.window * fps)))
    windows = [{"t": round(i / fps, 2),
                "mean": round(float(np.mean(diffs[i:i + per])), 2)}
               for i in range(0, len(diffs), per)]

    dead = runs_below(windows, args.dead, args.window)
    still = runs_below(windows, args.still, args.window)
    last = len(windows) - 1
    interior = [r for r in dead if r["i0"] > 0 and r["i1"] < last]
    long_dead = [r for r in dead if r["seconds"] >= 1.0]

    verdict = "dead" if (interior or long_dead) else "ok"
    result = {
        "file": args.clip,
        "fps": round(fps, 3),
        "duration": round(len(diffs) / fps, 2) if diffs else 0.0,
        "window": args.window,
        "dead_below": args.dead,
        "still_below": args.still,
        "windows": windows,
        "dead_runs": [[r["start"], r["end"]] for r in dead],
        "still_runs": [[r["start"], r["end"]] for r in still],
        "interior_dead": [[r["start"], r["end"]] for r in interior],
        "verdict": verdict,
    }
    print(json.dumps(result, ensure_ascii=False))
    return 0 if verdict == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
