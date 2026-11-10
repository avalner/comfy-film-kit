from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import requests, time, hashlib
root=Path(r'I:\Video Generation\ComfyUI_windows_portable\ComfyUI\models\SEEDVR2')
name='seedvr2_ema_3b_fp16.safetensors'
size=6783018808
step=32*1024*1024
parts=root/'.download-parts-3b'
parts.mkdir(exist_ok=True)
def fetch(i):
    start=i*step; end=min(size,start+step)-1
    p=parts/str(i)
    if p.exists() and p.stat().st_size==end-start+1: return
    for attempt in range(4):
        try:
            r=requests.get(f'https://huggingface.co/numz/SeedVR2_comfyUI/resolve/main/{name}?part={i}',headers={'Range':f'bytes={start}-{end}'},timeout=(20,90))
            r.raise_for_status()
            if r.status_code!=206 or r.headers.get('Content-Range')!=f'bytes {start}-{end}/{size}' or len(r.content)!=end-start+1: raise ValueError('range mismatch')
            p.write_bytes(r.content); return
        except Exception:
            if attempt==3: raise
            time.sleep(2)
n=(size+step-1)//step
with ThreadPoolExecutor(8) as pool:
    futures=[pool.submit(fetch,i) for i in range(n)]
    for done,f in enumerate(as_completed(futures),1):
        f.result()
        if done%16==0 or done==n: print(f'Download {done}/{n} parts ({done*100//n}%)',flush=True)
out=root/(name+'.partial')
h=hashlib.sha256()
with out.open('wb') as w:
    for i in range(n):
        data=(parts/str(i)).read_bytes(); h.update(data); w.write(data)
assert h.hexdigest()=='2fd0e03a3dad24e07086750360727ca437de4ecd456f769856e960ae93e2b304',h.hexdigest()
out.rename(root/name)
for i in range(n): (parts/str(i)).unlink()
parts.rmdir()
print('3B FP16 downloaded and SHA256 verified',flush=True)
