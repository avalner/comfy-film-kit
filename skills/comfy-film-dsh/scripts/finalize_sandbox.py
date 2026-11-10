"""Run finalize.py unchanged, but with a workspace-write-safe temp directory.

DSH's workspace-write sandbox gives `tempfile.mkdtemp()` directories a DACL that
later opens inside them are denied — even by the process that created them. The
symptom is `finalize.py` dying in its stitch or ffmpeg step with "Permission
denied" for a path under `.pipeline/finalize-XXXXXXXX`. `Path.mkdir()` produces
an ordinary inheriting directory, so this wrapper swaps `mkdtemp` for an
equivalent that uses `mkdir`, then runs the controller's `finalize.py` with the
same arguments.

Usage: identical to finalize.py.

    python finalize_sandbox.py --project PROJECT --name NAME [--input FILE]
                               [--version vN] [--deliver-dir DIR]
"""
import random
import runpy
import string
import sys
import tempfile
from pathlib import Path

FINALIZE = Path("I:/Video Generation/Tools/comfy-film/scripts/finalize.py")


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


def main():
    if not FINALIZE.is_file():
        raise SystemExit(f"finalize.py not found at {FINALIZE}")
    tempfile.mkdtemp = safe_mkdtemp
    sys.argv = [str(FINALIZE)] + sys.argv[1:]
    runpy.run_path(str(FINALIZE), run_name="__main__")


if __name__ == "__main__":
    main()
