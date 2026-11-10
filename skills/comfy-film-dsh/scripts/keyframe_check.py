"""Compare two keyframes and report the background difference that will morph.

FL2VA interpolates between the first and the last frame. If the two stills show
the same scenery in different states (moss patches, foliage, water, framing),
the model animates that difference across the ten seconds — the "growing moss"
failure mode. This script quantifies it before you spend a render.

Usage:
    python keyframe_check.py FIRST.png LAST.png [--grid 6] [--save heat.png]

Outputs compact JSON: overall difference, worst cells, and a verdict.
Exit code 0 when the pair looks safe, 1 when it needs attention.
"""
import argparse
import json
import sys

import numpy as np
from PIL import Image, ImageDraw

SIZE = (304, 528)  # half of the 608x1056 canvas


def load(path):
    img = Image.open(path).convert("RGB")
    # cover-crop to the canvas ratio, then downscale for speed
    target_ratio = SIZE[0] / SIZE[1]
    w, h = img.size
    if w / h > target_ratio:
        new_w = int(round(h * target_ratio))
        img = img.crop(((w - new_w) // 2, 0, (w + new_w) // 2, h))
    else:
        new_h = int(round(w / target_ratio))
        img = img.crop((0, (h - new_h) // 2, w, (h + new_h) // 2))
    return img.resize(SIZE, Image.LANCZOS)


def analyse(a, b, grid, save=None):
    arr_a = np.asarray(a).astype(np.float32)
    arr_b = np.asarray(b).astype(np.float32)
    diff = np.abs(arr_a - arr_b).mean(axis=2)

    h, w = diff.shape
    cell_h, cell_w = h // grid, w // grid
    cells = []
    for gy in range(grid):
        for gx in range(grid):
            block = diff[gy * cell_h:(gy + 1) * cell_h, gx * cell_w:(gx + 1) * cell_w]
            cells.append({
                "row": gy, "col": gx,
                "mean": round(float(block.mean()), 2),
                "x": round((gx + 0.5) / grid, 2),
                "y": round((gy + 0.5) / grid, 2),
            })
    cells.sort(key=lambda c: c["mean"], reverse=True)

    overall = float(diff.mean())
    worst = cells[0]["mean"]

    if overall < 3.0 and worst < 8.0:
        verdict = "safe"
        advice = "Keyframes match closely; the model has little to morph."
    elif overall < 6.0 and worst < 14.0:
        verdict = "watch"
        advice = "Minor differences; acceptable if the story changes that area anyway."
    else:
        verdict = "risky"
        advice = ("Large background differences. Expect the model to animate them. "
                  "Build the last frame from the first by editing (add only the subject) "
                  "or start the film from the design frame.")

    result = {
        "overall_mean_diff": round(overall, 2),
        "worst_cell_mean_diff": worst,
        "worst_cells": cells[:5],
        "verdict": verdict,
        "advice": advice,
    }

    if save:
        heat = Image.fromarray(np.clip(diff * 3.0, 0, 255).astype(np.uint8)).convert("RGB")
        heat = heat.resize((SIZE[0] * 2, SIZE[1] * 2), Image.LANCZOS)
        sheet = Image.new("RGB", (SIZE[0] * 6 + 40, SIZE[1] * 2 + 30), (16, 16, 16))
        sheet.paste(a.resize((SIZE[0] * 2, SIZE[1] * 2), Image.LANCZOS), (0, 30))
        sheet.paste(b.resize((SIZE[0] * 2, SIZE[1] * 2), Image.LANCZOS), (SIZE[0] * 2 + 20, 30))
        sheet.paste(heat, (SIZE[0] * 4 + 40, 30))
        draw = ImageDraw.Draw(sheet)
        draw.text((8, 8), "FIRST", fill=(255, 235, 190))
        draw.text((SIZE[0] * 2 + 28, 8), "LAST", fill=(255, 235, 190))
        draw.text((SIZE[0] * 4 + 48, 8), "DIFFERENCE (x3)", fill=(255, 235, 190))
        draw.text((8, SIZE[1] * 2 + 8),
                  f"overall {overall:.2f} / worst {worst:.2f} -> {verdict}: {advice}",
                  fill=(220, 220, 220))
        sheet.save(save)
        result["heatmap"] = str(save)

    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("first")
    ap.add_argument("last")
    ap.add_argument("--grid", type=int, default=6)
    ap.add_argument("--save", help="write a side-by-side + heatmap PNG here")
    args = ap.parse_args()
    a, b = load(args.first), load(args.last)
    result = analyse(a, b, args.grid, args.save)
    result["first"] = args.first
    result["last"] = args.last
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["verdict"] != "risky" else 1


if __name__ == "__main__":
    sys.exit(main())
