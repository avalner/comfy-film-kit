/* Read-only upscale progress renderer; mirrors progress.js for the generation panel. */
const title = document.getElementById("title");
const segment = document.getElementById("segment");
const percent = document.getElementById("percent");
const bar = document.getElementById("bar");
const phase = document.getElementById("phase");
const detail = document.getElementById("detail");
const connection = document.getElementById("connection");

function render(d) {
  if (!d.exists) {
    title.textContent = "Апскейл не запущен";
    segment.textContent = "";
    percent.textContent = "—";
    bar.value = 0;
    phase.textContent = d.message || "Ожидание";
    detail.textContent = "";
    connection.textContent = d.work ? "Рабочая папка: " + d.work : "";
    return;
  }

  const name = (d.output || "").split(/[\\/]/).pop();
  title.textContent = d.active ? "Апскейл выполняется" : "Апскейл завершён";
  segment.textContent = name ? name : "";

  if (typeof d.percent === "number") {
    percent.textContent = d.percent.toFixed(0) + "%";
    bar.value = d.percent;
  } else {
    percent.textContent = "—";
    bar.value = 0;
  }

  const parts = [];
  if (d.chunk && d.chunks) parts.push("чанк " + d.chunk + " из " + d.chunks);
  if (d.phase_name) parts.push(d.phase_name);
  if (d.batch && d.batches) parts.push("батч " + d.batch + "/" + d.batches);
  phase.textContent = parts.length ? parts.join(" · ") : "Ожидание данных";

  const bits = [];
  if (typeof d.frames_done === "number") {
    let s = "кадров готово: " + d.frames_done;
    if (d.frames_total) s += " из " + d.frames_total;
    bits.push(s);
  }
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
    connection.textContent = "Нет связи с панелью: " + e.message;
  }
}

tick();
setInterval(tick, 2000);
