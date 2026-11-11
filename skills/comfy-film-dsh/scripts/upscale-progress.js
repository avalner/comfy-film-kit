/* Read-only upscale progress renderer; mirrors progress.js for the generation panel. */
const I18N = {
  en: {
    pageTitle: "Upscale progress",
    notStarted: "Upscale not started",
    running: "Upscale running",
    finished: "Upscale finished",
    waiting: "Waiting",
    waitingData: "Waiting for data",
    work: "Working folder: ",
    chunk: (a, b) => `chunk ${a} of ${b}`,
    batch: (a, b) => `batch ${a}/${b}`,
    frames: (d, t) => t ? `frames done: ${d} of ${t}` : `frames done: ${d}`,
    noLink: e => "No connection to the panel: " + e,
    phases: {1: "VAE encoding", 2: "DiT upscale", 3: "VAE decoding", 4: "Post-processing"},
    footnote: "The percentage is the finished chunks plus the fraction of the running chunk. Frames reach the disk at chunk boundaries, so the frame counter moves in jumps."
  },
  ru: {
    pageTitle: "Прогресс апскейла",
    notStarted: "Апскейл не запущен",
    running: "Апскейл выполняется",
    finished: "Апскейл завершён",
    waiting: "Ожидание",
    waitingData: "Ожидание данных",
    work: "Рабочая папка: ",
    chunk: (a, b) => `чанк ${a} из ${b}`,
    batch: (a, b) => `батч ${a}/${b}`,
    frames: (d, t) => t ? `кадров готово: ${d} из ${t}` : `кадров готово: ${d}`,
    noLink: e => "Нет связи с панелью: " + e,
    phases: {1: "VAE-кодирование", 2: "DiT-апскейл", 3: "VAE-декодирование", 4: "Пост-обработка"},
    footnote: "Процент складывается из готовых чанков и доли текущего чанка. Кадры попадают на диск на границах чанков, поэтому счётчик кадров обновляется рывками."
  }
};
const forced = (new URLSearchParams(location.search).get("lang") || "").toLowerCase();
function pickLang(tag) {
  const raw = (forced || tag || window.FILM_LANG || "en").toLowerCase();
  return raw.startsWith("ru") ? "ru" : "en";
}
let lang = pickLang(), L = I18N[lang];

const title = document.getElementById("title");
const segment = document.getElementById("segment");
const percent = document.getElementById("percent");
const bar = document.getElementById("bar");
const phase = document.getElementById("phase");
const detail = document.getElementById("detail");
const connection = document.getElementById("connection");
const footnote = document.getElementById("footnote");

function useLang(tag) {
  const next = pickLang(tag);
  if (next === lang) return;
  lang = next; L = I18N[lang];
  document.documentElement.lang = lang;
  document.title = L.pageTitle;
  footnote.textContent = L.footnote;
}

function render(d) {
  useLang(d.lang);
  document.documentElement.lang = lang;
  document.title = L.pageTitle;
  footnote.textContent = L.footnote;
  if (!d.exists) {
    title.textContent = L.notStarted;
    segment.textContent = "";
    percent.textContent = "—";
    bar.value = 0;
    phase.textContent = L.waiting;
    detail.textContent = "";
    connection.textContent = d.work ? L.work + d.work : "";
    return;
  }

  const name = (d.output || "").split(/[\\/]/).pop();
  title.textContent = d.active ? L.running : L.finished;
  segment.textContent = name ? name : "";

  if (typeof d.percent === "number") {
    percent.textContent = d.percent.toFixed(0) + "%";
    bar.value = d.percent;
  } else {
    percent.textContent = "—";
    bar.value = 0;
  }

  const parts = [];
  if (d.chunk && d.chunks) parts.push(L.chunk(d.chunk, d.chunks));
  const phaseName = L.phases[d.phase] || d.phase_name;
  if (phaseName) parts.push(phaseName);
  if (d.batch && d.batches) parts.push(L.batch(d.batch, d.batches));
  phase.textContent = parts.length ? parts.join(" · ") : L.waitingData;

  const bits = [];
  if (typeof d.frames_done === "number") bits.push(L.frames(d.frames_done, d.frames_total));
  detail.textContent = bits.join(" · ");
  connection.textContent = d.last_line ? d.last_line.slice(0, 160) : "";
}

async function tick() {
  try {
    const r = await fetch("/api", { cache: "no-store" });
    if (!r.ok) throw new Error("HTTP " + r.status);
    render(await r.json());
    connection.title = "";
  } catch (e) {
    connection.textContent = L.noLink(e.message);
  }
}

tick();
setInterval(tick, 2000);
