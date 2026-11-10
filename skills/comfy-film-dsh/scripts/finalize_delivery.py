"""Finalize + delivery upscale in one command (the series default).

Runs the controller's `finalize.py` exactly as `finalize_sandbox.py` does (safe temp directory), then
upscales the accepted export with SeedVR2 and copies it next to the original and into the
deliver directory. Upscaling is on by default; pass `--no-upscale` for an exceptional film, `--scale N`
to change the factor.

    python finalize_delivery.py --project PROJECT --name NAME [--version vN]
                                [--deliver-dir DIR] [--input FILE]
                                [--scale 2] [--no-upscale] [--crf 16]
"""
import contextlib
import io
import json
import random
import runpy
import shutil
import string
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
FINALIZE = Path("I:/Video Generation/Tools/comfy-film/scripts/finalize.py")
UPSCALE = HERE / "upscale_seedvr2.py"

OWN_FLAGS = {"--no-upscale", "--scale", "--crf"}


def safe_mkdtemp(prefix=None, dir=None):
    for _ in range(200):
        name = (prefix or "tmp") + "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
        path = Path(dir) / name
        try:
            path.mkdir()
            return str(path)
        except FileExistsError:
            continue
    raise FileExistsError("could not create a temp directory")


def split_args(argv):
    passthrough, scale, crf, upscale = [], 2, 16, True
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--no-upscale":
            upscale = False
        elif a == "--scale":
            i += 1
            scale = int(argv[i])
        elif a.startswith("--scale="):
            scale = int(a.split("=", 1)[1])
        elif a == "--crf":
            i += 1
            crf = int(argv[i])
        elif a.startswith("--crf="):
            crf = int(a.split("=", 1)[1])
        else:
            passthrough.append(a)
        i += 1
    return passthrough, scale, crf, upscale


def main():
    if not FINALIZE.is_file():
        raise SystemExit(f"finalize.py not found at {FINALIZE}")
    args, scale, crf, upscale = split_args(sys.argv[1:])
    tempfile.mkdtemp = safe_mkdtemp
    buf = io.StringIO()
    code = 0
    sys.argv = [str(FINALIZE)] + args
    try:
        with contextlib.redirect_stdout(buf):
            runpy.run_path(str(FINALIZE), run_name="__main__")
    except SystemExit as e:
        code = e.code or 0
    except Exception as e:  # finalize failed; show its own output
        sys.stderr.write(buf.getvalue())
        raise
    out = buf.getvalue()
    try:
        result = json.loads(out.strip().splitlines()[-1])
    except Exception:
        sys.stderr.write(out)
        raise SystemExit("could not read finalize.py result")
    file = Path(result["file"])
    print(json.dumps({"finalize": result}, ensure_ascii=False), flush=True)
    if code not in (0, None):
        return code
    if not upscale:
        print(json.dumps({"upscale": "skipped"}, ensure_ascii=False))
        return 0

    target = file.with_name(f"{file.stem}-{scale}x{file.suffix}")
    if target.exists():
        raise SystemExit(f"refusing to overwrite {target}; bump the version")
    cmd = [sys.executable, str(UPSCALE), "--input", str(file), "--output", str(target),
           "--scale", str(scale), "--crf", str(crf)]
    print(json.dumps({"upscale": "running", "command": cmd}), flush=True)
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.stderr.write(proc.stdout + proc.stderr)
        raise SystemExit(f"upscale failed with {proc.returncode}")
    up = json.loads(proc.stdout.strip().splitlines()[-1]) if proc.stdout.strip() else {}
    if not up:
        raise SystemExit("upscale produced no result")
    delivered = None
    if "--deliver-dir" in args:
        deliver = Path(args[args.index("--deliver-dir") + 1]).resolve()
        deliver.mkdir(parents=True, exist_ok=True)
        delivered = deliver / target.name
        shutil.copy2(target, delivered)
    print(json.dumps({"upscale": up, "delivered": str(delivered) if delivered else None},
                     ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
