"""Lint a MiniMax H3 film prompt before submitting it to ComfyUI.

Checks the structural rules of the H3 guide (references/base-en.txt) plus the
project rules learned in production: no negative word lists, exact timecode
format, style line, static-shot phrasing.

Usage:
    python prompt_lint.py PROMPT.txt [--frames 243] [--static]

Exit code 0 when clean, 1 when issues were found. Always prints compact JSON.
"""
import argparse
import json
import re
import sys
from pathlib import Path

STYLE_WORDS = (
    "live-action", "cinematic", "2d-animated", "3d cg", "claymation",
    "watercolor", "watercolour", "vintage film", "animated", "photoreal",
)

# Concepts that should not be listed as prohibitions: naming them steers the model.
NEGATIVE_PATTERNS = [
    r"\bno\s+(?:sprout\w*|swell\w*|grow\w*|growth|spik\w*|wither\w*|melt\w*)",
    r"\bno\s+(?:droplet\w*|bead\w*|dew)\b",
    r"\bno\s+(?:crumb\w*|dust|particle\w*|debris)\b",
    r"\bnever\s+(?:sprout\w*|swell\w*|grow\w*|spik\w*|melt\w*)",
    r"\bwithout\s+(?:any\s+)?(?:sprout\w*|swell\w*|spik\w*|dust|debris)",
]


def lint(text: str, frames: int, static: bool):
    issues = []
    notes = []

    header = text.strip().splitlines()[0] if text.strip() else ""
    fl2va = header.startswith("How the reference pictures align")
    i2va = header.startswith("For the target video, at 0.00 seconds")
    if not (fl2va or i2va):
        issues.append({
            "code": "header",
            "message": "First line must be the FL2VA alignment sentence or the I2VA first-frame sentence",
        })

    for field in ("integrated_multimodal_description:", "overall_soundscape:", "non_diegetic_music:"):
        if field not in text:
            issues.append({"code": "field", "message": f"Missing field {field}"})

    if "[Shot 1]" not in text:
        issues.append({"code": "shot", "message": "Missing [Shot 1] marker"})

    # Duration in the header must be the real duration to two decimals.
    # Half-up rounding: 243 frames = 10.125 s -> 10.13, matching production prompts.
    seconds = frames / 24
    expected = f"{int(seconds * 100 + 0.5) / 100:.2f}"
    body_header = header
    marks = re.findall(r"(\d+\.\d{2})-second mark", body_header)
    if fl2va and len(marks) >= 1:
        last = marks[-1]
        if last != expected:
            issues.append({
                "code": "timecode",
                "message": f"Header end time {last} does not match {frames} frames ({expected})",
            })
    elif fl2va and not marks:
        issues.append({"code": "timecode", "message": "Header has no 'S.SS-second mark' timecode"})

    # Beat timings must use two decimals and stay inside the duration.
    for value in re.findall(r"\b(\d{1,2}\.\d+)\s*(?:to|-)\s*(\d{1,2}\.\d+)\s*second", text):
        for v in value:
            if not re.fullmatch(r"\d{1,2}\.\d{2}", v):
                issues.append({"code": "timecode", "message": f"Beat time {v} is not S.SS"})
            elif float(v) > float(expected) + 1e-9:
                issues.append({"code": "timecode", "message": f"Beat time {v} exceeds {expected}"})

    shot1 = text.split("[Shot 1]", 1)[-1][:220].lower() if "[Shot 1]" in text else ""
    if not any(word in shot1 for word in STYLE_WORDS):
        issues.append({
            "code": "style",
            "message": "[Shot 1] should open with the visual style (Live-action, cinematic, ...)",
        })

    if static and "static shot" not in text.lower():
        issues.append({
            "code": "camera",
            "message": "Static-camera film but the prompt never says 'The camera holds a static shot'",
        })

    hits = []
    for pattern in NEGATIVE_PATTERNS:
        hits += re.findall(pattern, text, flags=re.IGNORECASE)
    if hits:
        issues.append({
            "code": "negatives",
            "message": "Negative concept list found; state the positive state instead",
            "matches": sorted(set(h.strip() for h in hits))[:8],
        })

    if "no " in text.lower() and len(re.findall(r"\bno\b", text, flags=re.IGNORECASE)) >= 5:
        notes.append("Many 'no' clauses; consider rewriting them as positive statements")

    if "Picture 1" in text and "Picture 2" in text and i2va:
        notes.append("Both pictures mentioned but the header is I2VA; FL2VA header expected")

    return {"ok": not issues, "frames": frames, "duration": expected,
            "kind": "FL2VA" if fl2va else ("I2VA" if i2va else "unknown"),
            "issues": issues, "notes": notes}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("prompt")
    ap.add_argument("--frames", type=int, default=243, help="generated frames (243 for 10 s)")
    ap.add_argument("--static", action="store_true", help="film uses a fixed camera")
    args = ap.parse_args()
    text = Path(args.prompt).read_text(encoding="utf-8-sig")
    result = lint(text, args.frames, args.static)
    result["file"] = str(Path(args.prompt).resolve())
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
