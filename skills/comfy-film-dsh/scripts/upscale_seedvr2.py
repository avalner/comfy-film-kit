"""SeedVR2 delivery upscale; preserve native FPS/audio and verify the playback copy."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from upscale_deliverable import FFMPEG, FFPROBE, probe, has_audio, run, sha256

BASE = Path('I:/Video Generation/ComfyUI_windows_portable')
PYTHON = BASE / 'python_embeded/python.exe'
CLI = BASE / 'ComfyUI/custom_nodes/ComfyUI-SeedVR2_VideoUpscaler/inference_cli.py'
MODELS = BASE / 'ComfyUI/models/SEEDVR2'


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--input', required=True)
    ap.add_argument('--output')
    ap.add_argument('--scale', type=int, default=2)
    ap.add_argument('--crf', type=int, default=16)
    ap.add_argument('--preset', default='medium')
    ap.add_argument('--batch-size', type=int, default=5)
    ap.add_argument('--chunk-size', type=int, default=65)
    ap.add_argument('--keep-temp', action='store_true')
    a = ap.parse_args()
    src = Path(a.input).resolve()
    out = Path(a.output).resolve() if a.output else src.with_name(src.stem + f'-{a.scale}x.mp4')
    if not src.is_file() or out.exists():
        ap.error('input missing or output already exists')
    if a.scale < 1 or a.batch_size < 5 or a.batch_size % 4 != 1 or a.chunk_size < a.batch_size:
        ap.error('positive scale, batch size 4n+1 >= 5 and chunk size >= batch size required')
    model = 'seedvr2_ema_3b_fp16.safetensors'
    for path in (PYTHON, CLI, MODELS / model, MODELS / 'ema_vae_fp16.safetensors'):
        if not path.is_file():
            ap.error(f'missing SeedVR2 dependency: {path}')
    info = probe(src)
    cache = src.parent / '.pipeline'
    cache.mkdir(exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix='seedvr2-', dir=cache))
    frames = work / 'frames'
    log = work / 'seedvr2.log'
    started = time.time()
    env = dict(os.environ, PYTHONUTF8='1')
    env['PATH'] = str(FFMPEG.parent) + os.pathsep + env.get('PATH', '')
    cmd = [PYTHON, '-X', 'utf8', CLI, src, '--output', frames, '--output_format', 'png',
           '--model_dir', MODELS, '--dit_model', model,
           '--resolution', str(min(info['width'], info['height']) * a.scale),
           '--batch_size', str(a.batch_size), '--chunk_size', str(a.chunk_size),
           '--temporal_overlap', '1', '--dit_offload_device', 'cpu',
           '--vae_offload_device', 'cpu', '--vae_encode_tiled', '--vae_decode_tiled']
    try:
        with log.open('w', encoding='utf-8') as handle:
            proc = subprocess.run([str(x) for x in cmd], env=env, stdout=handle, stderr=subprocess.STDOUT)
        if proc.returncode:
            raise RuntimeError(f'SeedVR2 exited {proc.returncode}; log: {log}')
        frames = frames / src.stem
        count = len(list(frames.glob('*.png')))
        if count != info['frames']:
            raise RuntimeError(f'SeedVR2 produced {count}/{info["frames"]} frames; log: {log}')
        audio = has_audio(src)
        encode = [FFMPEG, '-v', 'error', '-n', '-framerate', str(info['fps']),
                  '-start_number', '0', '-i', frames / (src.stem + '_%06d.png')]
        if audio:
            encode += ['-i', src, '-map', '0:v:0', '-map', '1:a:0', '-c:a', 'aac', '-b:a', '192k']
        encode += ['-frames:v', str(count), '-c:v', 'libx264', '-preset', a.preset,
                   '-crf', str(a.crf), '-pix_fmt', 'yuv420p', '-movflags', '+faststart', out]
        run(encode)
        up = probe(out)
        if (up['frames'] != info['frames'] or up['width'] != info['width'] * a.scale
                or up['height'] != info['height'] * a.scale or abs(up['fps'] - info['fps']) > 0.001):
            raise RuntimeError('upscaled dimensions/frame count/FPS mismatch')
        streams = json.loads(run([FFPROBE, '-v', 'error', '-show_streams', '-of', 'json', out]).stdout)['streams']
        video = next(s for s in streams if s['codec_type'] == 'video')
        if video['codec_name'] != 'h264' or video['pix_fmt'] != 'yuv420p':
            raise RuntimeError('incompatible playback format')
        if audio and not any(s['codec_type'] == 'audio' and s['codec_name'] == 'aac' for s in streams):
            raise RuntimeError('AAC soundtrack missing')
        run([FFMPEG, '-v', 'error', '-i', out, '-f', 'null', '-'])
        result = dict(input=str(src), output=str(out), source=info, upscaled=up,
                      scale=a.scale, engine='SeedVR2', model=model, frames_upscaled=count,
                      upscale_seconds=round(time.time()-started, 1), audio=audio,
                      decode='passed', sha256=sha256(out))
    except Exception:
        print(f'SeedVR2 failed; diagnostic files retained at {work}', file=sys.stderr)
        raise
    if not a.keep_temp:
        shutil.rmtree(work)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
