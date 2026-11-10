"""Assemble or finish a playback deliverable without accepting or publishing it."""
import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--project', required=True)
    ap.add_argument('--input', help='Existing finished candidate; otherwise stitch accepted clips')
    ap.add_argument('--name', required=True, help='Video filename stem, e.g. autumn-leaf-fawn')
    ap.add_argument('--version', help='e.g. v2; otherwise next unused vN')
    ap.add_argument('--deliver-dir', help='Optional user-facing outputs directory')
    ap.add_argument('--region', type=float, nargs=4)
    ap.add_argument('--reference', type=float, nargs=2)
    args = ap.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9 _-]*', args.name):
        ap.error('Name must be a plain filename stem')
    if bool(args.region) != bool(args.reference):
        ap.error('Lighting requires both --region and --reference')
    root = Path(args.project).resolve()
    cfg = json.loads((root / 'film.json').read_text(encoding='utf-8-sig'))['config']
    dest = Path(args.deliver_dir).resolve() if args.deliver_dir else root
    version = args.version
    if version and not re.fullmatch(r'v[1-9][0-9]*', version):
        ap.error('Version must be vN with N >= 1')
    if not version:
        n = 1
        while any((d / f'{args.name}-final-v{n}.mp4').exists() for d in (root, dest)):
            n += 1
        version = f'v{n}'
    filename = f'{args.name}-final-{version}.mp4'
    target, delivery = root / filename, dest / filename
    if target.exists() or delivery.exists():
        ap.error('Final version exists; choose a new version')
    def run(cmd):
        return subprocess.check_output([str(x) for x in cmd], stderr=subprocess.PIPE)
    def probe(path):
        return json.loads(run([cfg['ffprobe'], '-v', 'error', '-show_streams', '-show_format', '-of', 'json', path]))
    work = Path(tempfile.mkdtemp(prefix='finalize-', dir=root / '.pipeline'))
    source = Path(args.input).resolve() if args.input else work / 'assembly.mp4'
    if not args.input:
        run([sys.executable, Path(__file__).with_name('film.py'), 'stitch', '--project', root, '--output', source])
    if args.region:
        lit = work / 'lighting.mp4'
        run([sys.executable, Path(__file__).with_name('match_lighting.py'), '--input', source, '--output', lit,
             '--ffmpeg', cfg['ffmpeg'], '--ffprobe', cfg['ffprobe'], '--region', *args.region, '--reference', *args.reference])
        source = lit
    before = probe(source)
    streams = before['streams']
    video = next(s for s in streams if s['codec_type'] == 'video')
    audio = next((s for s in streams if s['codec_type'] == 'audio'), None)
    compatible = video['codec_name'] == 'h264' and video.get('pix_fmt') == 'yuv420p'
    candidate = work / filename
    cmd = [cfg['ffmpeg'], '-v', 'error', '-n', '-i', source, '-map', '0:v:0', '-map', '0:a:0?']
    cmd += ['-c:v', 'copy'] if compatible else ['-c:v', 'libx264', '-crf', '17', '-preset', 'fast', '-pix_fmt', 'yuv420p', '-profile:v', 'high']
    cmd += ['-tag:v', 'avc1', '-c:a', 'copy' if audio is None or audio['codec_name'] == 'aac' else 'aac', '-movflags', '+faststart', candidate]
    run(cmd)
    after = probe(candidate)
    v = next(s for s in after['streams'] if s['codec_type'] == 'video')
    if v['codec_name'] != 'h264' or v.get('pix_fmt') != 'yuv420p':
        raise RuntimeError('Playback compatibility verification failed')
    if any(s['codec_type'] == 'audio' and s['codec_name'] != 'aac' for s in after['streams']):
        raise RuntimeError('Audio compatibility verification failed')
    if any(v.get(k) != video.get(k) for k in ('width', 'height', 'nb_frames')):
        raise RuntimeError('Dimensions or frame count changed')
    run([cfg['ffmpeg'], '-v', 'error', '-i', candidate, '-f', 'null', '-'])
    # Exclusive creation prevents overwriting a version created by another process.
    def copy_exclusive(src, dst):
        dst.parent.mkdir(parents=True, exist_ok=True)
        with open(src, 'rb') as inp, open(dst, 'xb') as out:
            shutil.copyfileobj(inp, out)
    copy_exclusive(candidate, target)
    if delivery != target:
        copy_exclusive(target, delivery)
    report = {'file': str(target), 'delivery': str(delivery), 'codec': 'h264', 'pix_fmt': 'yuv420p',
              'frames': v.get('nb_frames'), 'duration': after['format']['duration'], 'decode': 'passed',
              'video_reencoded': not compatible, 'lighting_applied': bool(args.region),
              'review_status': 'pending', 'work': str(work)}
    (work / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(json.dumps({'error': str(exc), 'automatic_retry': False}))
        sys.exit(1)
