"""Live progress page for single-image generation (Codex imagegen and similar).

The image call itself is blocking and reports nothing while it runs, so this page
counts from a start marker written before the call: percent = elapsed / expected,
with a live "time left" and "finish at" line. After the call the marker is closed
with the real elapsed seconds and the produced file.

The page is English by default; pass --lang ru (or set COMFY_FILM_LANG=ru) when the
conversation with the user is Russian.

Usage
  python image-progress.py --state PATH --serve --port 54470 [--lang ru]
  python image-progress.py --state PATH --start --label "board-3 · kitten awake" --eta 60
  python image-progress.py --state PATH --done --file "...\\codex_...png"
  python image-progress.py --state PATH --fail --note "model error"
  python image-progress.py --state PATH --idle
"""

import argparse
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# English unless the conversation is Russian. Precedence: --lang, COMFY_FILM_LANG, en.
LANG_ENV = "COMFY_FILM_LANG"
LANGS = ("en", "ru")


def resolve_lang(value=None):
    """Normalise a language tag to a supported panel language (default English)."""
    for candidate in (value, os.environ.get(LANG_ENV)):
        if candidate:
            tag = str(candidate).strip().lower().replace("_", "-")[:2]
            if tag in LANGS:
                return tag
    return "en"


PAGE = """<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Image generation progress</title>
<style>
:root{color-scheme:dark;font:16px system-ui;background:#101822;color:#eaf2fa}
body{margin:0;padding:32px;display:grid;min-height:80vh;place-items:center}
main{width:min(560px,100%)}small{color:#93abc0}
h1{font-size:26px;margin:12px 0 4px;font-weight:640}
#percent{font-size:80px;font-weight:650;letter-spacing:-4px;margin-top:26px}
progress{width:100%;height:16px;accent-color:#8cd9ff}
#phase{font-size:20px;margin-top:22px}#detail{color:#afc4d5;min-height:3em}
#eta{font-size:17px;margin-top:2px}
footer{border-top:1px solid #304052;margin-top:32px;padding-top:16px;color:#93abc0;line-height:1.6}
</style>
<main><small>CODEX · IMAGE</small><h1 id="title">Connecting…</h1><small id="sub"></small>
<div id="percent">—</div><progress id="bar" max="100"></progress>
<div id="phase">Waiting</div><p id="detail"></p><p id="eta"></p>
<footer id="foot">The percentage counts elapsed time against the expected generation time;
after that only the file save remains.</footer></main>
<script>window.FILM_LANG="__LANG__";</script>
<script>
const I18N = {
  en: {
    locale:'en-GB',
    pageTitle:'Image generation progress',
    defaultTitle:'Image generation',
    connecting:'Connecting…',
    running:'Rendering frame',
    done:'Done',
    failed:'Failed',
    idle:'Waiting',
    elapsed:(a,b)=>`Elapsed ${a} of expected ${b}`,
    ready:(t,f)=>`Frame ready in ${t}${f?' · '+f:''}`,
    failedNote:'Generation failed',
    nothing:'Nothing is being generated right now',
    left:(l,f)=>`≈ ${l} left · finish ≈ ${f}`,
    finishedAt:f=>`Finished at ${f}`,
    history:h=>'Recent frames: '+h,
    foot:'The percentage counts elapsed time against the expected generation time.',
    span:(m,s)=>m?`${m} min ${s} s`:`${s} s`
  },
  ru: {
    locale:'ru-RU',
    pageTitle:'Прогресс генерации изображения',
    defaultTitle:'Генерация изображения',
    connecting:'Подключение…',
    running:'Генерация кадра',
    done:'Готово',
    failed:'Ошибка',
    idle:'Ожидание',
    elapsed:(a,b)=>`Прошло ${a} из ожидаемых ${b}`,
    ready:(t,f)=>`Кадр готов за ${t}${f?' · '+f:''}`,
    failedNote:'Генерация не удалась',
    nothing:'Сейчас ничего не генерируется',
    left:(l,f)=>`Осталось ≈ ${l} · финиш ≈ ${f}`,
    finishedAt:f=>`Завершено в ${f}`,
    history:h=>'Последние кадры: '+h,
    foot:'Процент считается по прошедшему времени от ожидаемой длительности генерации.',
    span:(m,s)=>m?`${m} мин ${s} с`:`${s} с`
  }
};
const forced=(new URLSearchParams(location.search).get('lang')||'').toLowerCase();
function pickLang(tag){
  const raw=(forced||tag||window.FILM_LANG||'en').toLowerCase();
  return raw.startsWith('ru')?'ru':'en';
}
let lang=pickLang(), L=I18N[lang];
const $ = id => document.getElementById(id);
let cfg = null, tick = 0;
function clock(sec){const t=new Date(Date.now()+sec*1000);
  return t.toLocaleTimeString(L.locale,{hour:'2-digit',minute:'2-digit',second:'2-digit'});}
function fmt(s){s=Math.max(0,Math.round(s));const m=Math.floor(s/60);return L.span(m,s%60);}
function render(){
  if(!cfg){return;}
  if((cfg.lang||'en')!==lang&&!forced){lang=pickLang(cfg.lang);L=I18N[lang];}
  document.documentElement.lang=lang;
  document.title=L.pageTitle;
  const now=Date.now()/1000;
  const running=cfg.status==='running';
  const eta=cfg.eta||60;
  let elapsed=cfg.elapsed||0, left=0, percent=0;
  if(running){elapsed=now-(cfg.started||now);left=Math.max(0,eta-elapsed);
    percent=Math.min(99,Math.round(elapsed/eta*100));}
  else if(cfg.status==='done'){percent=100;elapsed=cfg.seconds||elapsed;}
  $('title').textContent=cfg.title||L.defaultTitle;
  $('sub').textContent=cfg.label||'';
  $('percent').textContent = cfg.status==='idle' ? '—' : percent+'%';
  if(cfg.status==='idle'){$('bar').removeAttribute('value');}else{$('bar').value=percent;}
  $('phase').textContent = cfg.status==='running' ? L.running
    : cfg.status==='done' ? L.done : cfg.status==='failed' ? L.failed : L.idle;
  $('detail').textContent = cfg.status==='running'
      ? L.elapsed(fmt(elapsed), fmt(eta))
    : cfg.status==='done' ? L.ready(fmt(cfg.seconds||0), cfg.file?cfg.file.split(/[\\\\/]/).pop():'')
    : cfg.status==='failed' ? (cfg.note||L.failedNote)
    : L.nothing;
  $('eta').textContent = cfg.status==='running'
      ? L.left(fmt(left), clock(left))
    : cfg.status==='done' ? L.finishedAt(clock(0)) : '';
  $('foot').textContent = cfg.history && cfg.history.length
      ? L.history(cfg.history.slice(-4).map(h=>`${h.label} — ${Math.round(h.seconds)} s`).join(' · '))
      : L.foot;
}
async function refresh(){try{const r=await fetch('/api',{cache:'no-store'});
  if(r.ok){cfg=await r.json();render();}}catch(_){}}
refresh(); setInterval(refresh,1500); setInterval(render,250);
</script></html>
"""


def load(path):
    p = Path(path)
    if not p.exists():
        return {"status": "idle", "history": []}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"status": "idle", "history": []}


def save(path, state):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)


def update(path, **kw):
    state = load(path)
    state.update(kw)
    save(path, state)
    return state


def serve(path, port, lang="en"):
    page = PAGE.replace("__LANG__", lang).encode("utf-8")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            if self.path.startswith("/api"):
                state = load(path)
                state.setdefault("lang", lang)
                body = json.dumps(state, ensure_ascii=False).encode("utf-8")
                ctype = "application/json; charset=utf-8"
            elif self.path.split("?", 1)[0] in ("/", "/index.html"):
                body = page
                ctype = "text/html; charset=utf-8"
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"image progress: http://127.0.0.1:{port}", flush=True)
    srv.serve_forever()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", required=True)
    ap.add_argument("--serve", action="store_true")
    ap.add_argument("--port", type=int, default=54470)
    ap.add_argument("--lang", choices=LANGS, default=None,
                    help=f"page language (default: ${LANG_ENV} or en)")
    ap.add_argument("--start", action="store_true")
    ap.add_argument("--done", action="store_true")
    ap.add_argument("--fail", action="store_true")
    ap.add_argument("--idle", action="store_true")
    ap.add_argument("--label", default="")
    ap.add_argument("--title", default="")
    ap.add_argument("--eta", type=float, default=60.0)
    ap.add_argument("--file", default="")
    ap.add_argument("--note", default="")
    a = ap.parse_args()

    if a.serve:
        serve(a.state, a.port, resolve_lang(a.lang))
        return
    if a.start:
        st = load(a.state)
        st.update(status="running", label=a.label, title=a.title, eta=a.eta,
                  started=time.time(), file="", note="", elapsed=0)
        save(a.state, st)
        print(json.dumps({"status": "running", "label": a.label, "eta": a.eta}, ensure_ascii=False))
        return
    if a.done:
        st = load(a.state)
        seconds = max(0.0, time.time() - st.get("started", time.time()))
        hist = st.get("history", [])
        hist.append({"label": st.get("label", ""), "seconds": seconds, "file": a.file,
                     "at": time.time()})
        st.update(status="done", seconds=seconds, elapsed=seconds, file=a.file,
                  history=hist[-20:])
        save(a.state, st)
        print(json.dumps({"status": "done", "seconds": round(seconds, 1)}, ensure_ascii=False))
        return
    if a.fail:
        update(a.state, status="failed", note=a.note)
        print(json.dumps({"status": "failed"}, ensure_ascii=False))
        return
    if a.idle:
        update(a.state, status="idle", label="")
        print(json.dumps({"status": "idle"}, ensure_ascii=False))
        return
    print(json.dumps(load(a.state), ensure_ascii=False))


if __name__ == "__main__":
    main()
