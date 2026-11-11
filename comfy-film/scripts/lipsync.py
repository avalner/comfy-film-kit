"""Lipsync: a character speaks or sings a supplied audio track.

One take, not a segment chain — the video follows the audio, so there is nothing to continue.
The graph is MiniMax H3 Singularity Ref2V + `MiniMaxH3NativeAudioLock`, two passes: 12 steps,
the second half of the schedule finishes an upscaled latent, and the saved file keeps the
original audio instead of a regenerated one.

    python lipsync.py --audio voice.mp3 --ref face.png --prompt-file part.txt --out take.mp4
    python lipsync.py --project "I:/Video Generation/Projects/<film>" ...   # writes clips/lipsync-000N.mp4

The models it needs are installed by `setup/install-comfy.ps1 -Modes lipsync`; names are resolved
from ComfyUI's own object_info, so an existing copy in a subfolder is found too.
"""

import argparse
import json
import random
import sys
import time
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import film  # noqa: E402  the controller: config defaults, HTTP helpers, upload

FPS = 24
REQUIRED = [
    "MiniMaxH3ReferenceToVideo", "MiniMaxH3NativeAudioLock", "ModelAttentionBackend",
    "LTXVSeparateAVLatent", "LTXVConcatAVLatent", "SplitSigmas", "MinimaxH3LatentUpscaler3D",
    "LoadAudio", "KSamplerSelect", "BasicScheduler", "BasicGuider", "SamplerCustomAdvanced",
    "VAEDecode", "CreateVideo", "SaveVideo", "UNETLoader", "CLIPLoader", "VAELoader",
]


def frames(seconds):
    """H3 length: 24 fps on its 17k+5 frame grid."""
    f = max(5, round(seconds * FPS))
    return f + (5 - f % 17) % 17


def object_info(config, node):
    with urllib.request.urlopen(config["server"].rstrip("/") + "/object_info/" + node, timeout=30) as r:
        return json.load(r)


def options(config, node, field):
    """A combo's choices: both the old [[...], {}] shape and the newer ["COMBO", {"options": [...]}]."""
    info = object_info(config, node).get(node, {})
    spec = info.get("input", {}).get("required", {}).get(field)
    if not spec:
        raise film.FilmError(f"Cannot list {node}.{field} from ComfyUI")
    head = spec[0]
    if isinstance(head, list):
        return head
    if isinstance(spec[1], dict) and isinstance(spec[1].get("options"), list):
        return [o if isinstance(o, str) else o.get("key") for o in spec[1]["options"]]
    raise film.FilmError(f"{node}.{field} is not a fixed list in this ComfyUI")


def pick(names, wanted, label, override=None):
    if override:
        if override in names:
            return override
        leaf = override.replace("/", "\\")
        for n in names:
            if n.replace("/", "\\") == leaf or n.split("\\")[-1] == override.split("/")[-1]:
                return n
        raise film.FilmError(f"{label}: '{override}' is not in ComfyUI's list. Available: "
                             + ", ".join(sorted(names)[:12]))
    for needle in wanted:
        for n in names:
            if needle in n.lower():
                return n
    raise film.FilmError(f"{label}: nothing matching {wanted} in ComfyUI. Available: "
                         + ", ".join(sorted(names)[:12])
                         + f". Install it with: setup/install-comfy.ps1 -Modes lipsync")


def wrap_prompt(text, n_refs):
    """H3's structured prompt, unless the caller already wrote one."""
    if "integrated_multimodal_description" in text:
        return text
    refs = " ".join(f"<Picture {i}> (from [Shot 1]) is fully referenced." for i in range(1, n_refs + 1))
    return (f"For the target video, at 0.00 seconds into the target video, {refs}\n\n"
            f"integrated_multimodal_description: [Shot 1] {text}\n\n"
            "overall_soundscape: N/A\n\nnon_diegetic_music: N/A")


def build_graph(names, prompt, width, height, length, seed, audio_name, refs, scale, steps, split):
    graph = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": names["unet"], "weight_dtype": "default"}},
        "2": {"class_type": "ModelAttentionBackend", "inputs": {
            "model": ["1", 0], "attention": "comfy kitchen attention"}},
        "3": {"class_type": "LoraLoaderModelOnly", "inputs": {
            "model": ["2", 0], "lora_name": names["lora"], "strength_model": names["lora_strength"]}},
        "4": {"class_type": "CLIPLoader", "inputs": {"clip_name": names["clip"], "type": "minimax", "device": "default"}},
        "5": {"class_type": "VAELoader", "inputs": {"vae_name": names["video_vae"]}},
        "6": {"class_type": "VAELoader", "inputs": {"vae_name": names["audio_vae"]}},
        "7": {"class_type": "LoadAudio", "inputs": {"audio": audio_name}},
        "8": {"class_type": "MiniMaxH3ReferenceToVideo", "inputs": {
            "clip": ["4", 0], "vae": ["5", 0], "audio_vae": ["6", 0], "prompt": prompt,
            "width": width, "height": height, "length": length, "ref_image_size": "match"}},
        "9": {"class_type": "MiniMaxH3NativeAudioLock", "inputs": {
            "model": ["1", 0], "av_latent": ["8", 1], "audio_vae": ["6", 0], "audio": ["7", 0]}},
        "10": {"class_type": "BasicScheduler", "inputs": {
            "model": ["9", 0], "scheduler": "beta", "steps": steps, "denoise": 1.0}},
        "11": {"class_type": "SplitSigmas", "inputs": {"sigmas": ["10", 0], "step": split}},
        "12": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
        "13": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
        "14": {"class_type": "BasicGuider", "inputs": {"model": ["3", 0], "conditioning": ["8", 0]}},
        "15": {"class_type": "SamplerCustomAdvanced", "inputs": {
            "noise": ["12", 0], "guider": ["14", 0], "sampler": ["13", 0],
            "sigmas": ["11", 0], "latent_image": ["9", 1]}},
        "16": {"class_type": "LTXVSeparateAVLatent", "inputs": {"av_latent": ["15", 1]}},
        "17": {"class_type": "MinimaxH3LatentUpscaler3D", "inputs": {
            "latent": ["16", 0], "model_name": names["upscaler"], "mode": "scale by multiplier",
            "mode.scale": scale, "align": 32, "enable_temporal_chunking": True, "force_unload": True,
            "device": "cuda", "precision": "fp16"}},
        "18": {"class_type": "LTXVConcatAVLatent", "inputs": {
            "video_latent": ["17", 0], "audio_latent": ["16", 1]}},
        "19": {"class_type": "SamplerCustomAdvanced", "inputs": {
            "noise": ["12", 0], "guider": ["14", 0], "sampler": ["13", 0],
            "sigmas": ["11", 1], "latent_image": ["18", 0]}},
        "20": {"class_type": "VAEDecode", "inputs": {"samples": ["19", 1], "vae": ["5", 0]}},
        "21": {"class_type": "CreateVideo", "inputs": {
            "images": ["20", 0], "audio": ["9", 2], "fps": float(FPS),
            "bit_depth": "auto", "color_space": "sRGB", "codec": "none"}},
        "22": {"class_type": "SaveVideo", "inputs": {
            "video": ["21", 0], "filename_prefix": "comfy_film/lipsync",
            "format": "auto", "format.codec": "auto"}},
    }
    for i, name in enumerate(refs[:9]):
        node = str(30 + i)
        graph[node] = {"class_type": "LoadImage", "inputs": {"image": name}}
        graph["8"]["inputs"][f"ref_images.ref_image_{i}"] = [node, 0]
    return graph


def find_output(entry):
    """First saved file in a history entry, whatever key SaveVideo uses."""
    for output in entry.get("outputs", {}).values():
        for value in output.values():
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict) and item.get("filename"):
                        return item
    return None


def wait_for(config, prompt_id, timeout):
    started = time.time()
    last_note = 0.0
    while time.time() - started < timeout:
        with urllib.request.urlopen(config["server"].rstrip("/") + "/history/" + prompt_id, timeout=30) as r:
            history = json.load(r)
        entry = history.get(prompt_id)
        if entry:
            status = entry.get("status", {})
            if status.get("status_str") == "error":
                messages = [m for m in status.get("messages", []) if m and m[0] == "execution_error"]
                detail = messages[0][1].get("exception_message", "") if messages else ""
                raise film.FilmError("ComfyUI failed: " + (detail or "execution_error"))
            if status.get("completed"):
                return entry
        elapsed = int(time.time() - started)
        if elapsed - last_note >= 20:
            last_note = elapsed
            print(f"  ... {elapsed} s", flush=True)
        time.sleep(3)
    raise film.FilmError(f"Timed out after {timeout} s; the job may still be running in ComfyUI")


def run(args):
    project = Path(args.project).resolve() if args.project else None
    if project and (project / "film.json").exists():
        record = film.read(project / "film.json")
        config = record["config"]
        root = project
    else:
        config = film.defaults()
        root = project

    film.ensure_server(config)

    missing = []
    for node in REQUIRED:
        try:
            if node not in object_info(config, node):
                missing.append(node)
        except Exception:
            missing.append(node)
    if missing:
        raise film.FilmError("ComfyUI has no " + ", ".join(missing)
                             + ". Install them with: setup/install-comfy.ps1 -Modes lipsync")

    names = {
        "unet": pick(options(config, "UNETLoader", "unet_name"), ["singularity", "ref2va", "h3"], "unet", args.unet),
        "lora": pick(options(config, "LoraLoaderModelOnly", "lora_name"), ["ref2v_turbo", "turbo_4step", "turbo"],
                     "lipsync LoRA", args.lora),
        "clip": pick(options(config, "CLIPLoader", "clip_name"), ["qwen3vl_32b", "minimax", "qwen3vl"],
                     "text encoder", args.clip),
        "video_vae": pick(options(config, "VAELoader", "vae_name"), ["video_vae"], "video VAE", args.video_vae),
        "audio_vae": pick(options(config, "VAELoader", "vae_name"), ["audio_vae"], "audio VAE", args.audio_vae),
        "upscaler": pick(options(config, "MinimaxH3LatentUpscaler3D", "model_name"),
                         ["latent_upscaler_3d"], "latent upscaler", args.upscaler),
        "lora_strength": args.lora_strength,
    }

    audio = Path(args.audio).resolve()
    if not audio.is_file():
        raise film.FilmError(f"No such audio file: {audio}")
    duration = json.loads(film.run_process([config["ffprobe"], "-v", "error", "-show_format", "-of", "json", str(audio)]))
    seconds = float(duration["format"]["duration"])
    if args.seconds:
        seconds = min(seconds, args.seconds)
    length = frames(seconds)

    refs = []
    for path in args.ref:
        p = Path(path).resolve()
        if not p.is_file():
            raise film.FilmError(f"No such reference image: {p}")
        refs.append(p)
    if not refs:
        raise film.FilmError("At least one reference picture is required (--ref), up to nine.")

    prompt_text = Path(args.prompt_file).read_text(encoding="utf-8").strip() if args.prompt_file else args.prompt
    if not prompt_text:
        raise film.FilmError("Give the prompt with --prompt or --prompt-file")
    prompt = wrap_prompt(prompt_text, len(refs))

    seed = args.seed if args.seed is not None else random.randint(1, 2 ** 31 - 1)
    tag = "lipsync"
    audio_name = film.upload(config, audio, "comfy_film/" + tag)
    ref_names = [film.upload(config, p, "comfy_film/" + tag) for p in refs]

    graph = build_graph(names, prompt, args.width, args.height, length, seed, audio_name, ref_names,
                        args.scale, args.steps, args.split)

    if args.dry_run:
        film.emit({"status": "dry-run", "nodes": len(graph), "frames": length, "seconds": round(seconds, 2),
                   "seed": seed, "models": {k: v for k, v in names.items() if k != "lora_strength"},
                   "refs": len(refs), "scale": args.scale, "steps": args.steps, "split": args.split})
        return

    client_id = str(uuid.uuid4())
    queued = film.api(config, "/prompt", {"prompt": graph, "client_id": client_id})
    prompt_id = queued.get("prompt_id")
    if not prompt_id:
        raise film.FilmError("ComfyUI rejected the graph: " + json.dumps(queued)[:400])
    print(f"  queued {prompt_id} — {length} frames, {seconds:.2f} s of audio", flush=True)

    entry = wait_for(config, prompt_id, args.timeout)
    item = find_output(entry)
    if not item:
        raise film.FilmError("Finished, but no video in the history outputs")

    query = urllib.parse.urlencode({"filename": item["filename"], "subfolder": item.get("subfolder", ""),
                                    "type": item.get("type", "output")})
    with urllib.request.urlopen(config["server"].rstrip("/") + "/view?" + query, timeout=300) as r:
        payload = r.read()

    if args.out:
        target = Path(args.out).resolve()
    elif root:
        clip_dir = root / "clips"
        clip_dir.mkdir(parents=True, exist_ok=True)
        existing = [p for p in clip_dir.glob("lipsync-*.mp4") if p.stem.split("-")[-1].isdigit()]
        number = max([int(p.stem.split("-")[-1]) for p in existing], default=0) + 1
        target = clip_dir / f"lipsync-{number:04d}.mp4"
    else:
        target = Path.cwd() / f"lipsync-{time.strftime('%Y%m%d-%H%M%S')}.mp4"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)

    info = film.probe(config, target)
    record = {
        "status": "ok", "file": str(target), "prompt_id": prompt_id, "seed": seed,
        "width": info["width"], "height": info["height"], "fps": info["fps"],
        "duration": round(info["duration"], 3), "frames": info["frames"], "audio": info["audio"],
        "models": names, "scale": args.scale, "steps": args.steps, "split": args.split,
        "refs": [str(p) for p in refs], "audio_source": str(audio),
    }
    if root:
        journal = root / ".pipeline" / "lipsync"
        journal.mkdir(parents=True, exist_ok=True)
        film.write(journal / f"{target.stem}.json", record)
    film.emit(record)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--audio", required=True, help="speech or song the character must follow")
    ap.add_argument("--ref", action="append", default=[], help="reference picture (repeatable, 1-9)")
    ap.add_argument("--prompt", default="", help="what the character does")
    ap.add_argument("--prompt-file", default="", help="file with the prompt (wins over --prompt)")
    ap.add_argument("--project", default="", help="film project: config comes from film.json, output to clips/")
    ap.add_argument("--out", default="", help="explicit output file")
    ap.add_argument("--width", type=int, default=768)
    ap.add_argument("--height", type=int, default=1344)
    ap.add_argument("--seconds", type=float, default=0.0, help="cut the video shorter than the audio")
    ap.add_argument("--scale", type=float, default=2.0, help="latent upscale of the second pass")
    ap.add_argument("--steps", type=int, default=12)
    ap.add_argument("--split", type=int, default=8, help="step where the second pass takes over")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--lora-strength", type=float, default=0.55)
    ap.add_argument("--unet", default="")
    ap.add_argument("--lora", default="")
    ap.add_argument("--clip", default="")
    ap.add_argument("--video-vae", default="")
    ap.add_argument("--audio-vae", default="")
    ap.add_argument("--upscaler", default="")
    ap.add_argument("--timeout", type=int, default=3600)
    ap.add_argument("--dry-run", action="store_true", help="build and check the graph, queue nothing")
    args = ap.parse_args(argv)
    try:
        run(args)
    except film.FilmError as e:
        film.emit({"status": "error", "error": str(e)})
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
