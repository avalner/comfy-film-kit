/* Pure reducer is also exercised with recorded/synthetic ComfyUI events. */
function reduceProgress(state, message, config) {
  const d = message.data || {};
  if (d.prompt_id && d.prompt_id !== config.prompt) return state;
  const next = {...state};
  const samplingNodes = config.samplers || [config.generator];
  const isSampler = id => samplingNodes.some(node => id === node || (id || '').startsWith(node + ':'));
  if (message.type === 'progress_state') {
    for (const [id, node] of Object.entries(d.nodes || {})) {
      if (isSampler(id) && node.max > 1) {
        next.value = node.value; next.max = node.max;
      }
    }
  }
  if (message.type === 'progress' && d.max > 1 &&
      isSampler(d.node)) {
    next.value = d.value; next.max = d.max;
  }
  if (message.type === 'executing' && d.node) next.node = d.node;
  if (message.type === 'execution_error' || message.type === 'execution_interrupted') next.error = true;
  return next;
}

if (typeof module !== 'undefined') module.exports = {reduceProgress};
if (typeof document !== 'undefined') {
  const $ = id => document.getElementById(id);
  let config = {}, state = {}, socket, socketClient, busy = false;
  const timing = {value: null, at: null, perStep: null, decode: 32};
  function clock(sec) {
    const t = new Date(Date.now() + sec * 1000);
    return t.toLocaleTimeString('ru-RU', {hour: '2-digit', minute: '2-digit', second: '2-digit'});
  }
  function etaText() {
    if (config.status !== 'running' || !state.max) return '';
    const now = Date.now() / 1000;
    if (state.value !== timing.value) {
      if (timing.value !== null && timing.at !== null && state.value > timing.value) {
        const sample = (now - timing.at) / (state.value - timing.value);
        timing.perStep = timing.perStep ? timing.perStep * 0.65 + sample * 0.35 : sample;
      }
      timing.value = state.value; timing.at = now;
    }
    if (!timing.perStep) return '';
    const left = Math.max(0, state.max - state.value) * timing.perStep +
      (state.value < state.max ? timing.decode : timing.decode * 0.5);
    const m = Math.floor(left / 60), s = Math.round(left % 60);
    return `Осталось ≈ ${m ? m + ' мин ' : ''}${s} с · финиш ≈ ${clock(left)}`;
  }
  function render() {
    $('title').textContent = config.title || 'ComfyUI';
    $('segment').textContent = config.segment ? `Фрагмент ${config.segment}` : '';
    const done = ['review', 'accepted'].includes(config.status);
    const failed = config.status === 'failed' || state.error;
    if (state.max) {
      const percent = Math.min(100, Math.round(state.value / state.max * 100));
      $('percent').textContent = percent + '%'; $('bar').value = percent;
      $('detail').textContent = `Шаг ${state.value} из ${state.max}`;
    } else {
      $('percent').textContent = '—'; $('bar').removeAttribute('value');
      $('detail').textContent = 'Ждём данные о шагах от ComfyUI';
    }
    timing.value = state.max ? state.value : null;
    $('eta').textContent = etaText();
    const label = config.labels?.[state.node] || state.node || '';
    $('phase').textContent = done ? 'Готово к просмотру' : failed ? 'Ошибка генерации' :
      config.status === 'rejected' ? 'Ожидание новой версии' :
      config.status === 'running' ? (state.max && state.value >= state.max ? 'Декодирование / сохранение' : state.max ? 'Расчёт шагов' : 'Подготовка / ожидание расчёта') : 'Ожидание запуска';
    if (!done && !failed && /decode/i.test(label)) $('phase').textContent = 'Декодирование';
    if (!done && !failed && /save|createvideo/i.test(label)) $('phase').textContent = 'Сохранение видео';
    if (done) {
      $('percent').textContent = '100%'; $('bar').value = 100;
      $('detail').textContent = 'Видео создано. Оценка результата — в чате.';
    }
    if (failed) $('detail').textContent = 'Генерация остановлена. Автоматического перезапуска нет.';
    $('connection').textContent = config.connection_warning ||
      (config.live?.connected ? 'Подключено · обновляется автоматически' : done ? 'Результат сохранён' : 'Подключение к событиям ComfyUI…');
  }
  function connect() {
    if (!config.client || config.status !== 'running') return;
    if (socketClient === config.client && socket && [0,1].includes(socket.readyState)) return;
    if (socket) { socket.onclose = null; socket.close(); }
    socketClient = config.client;
    socket = new WebSocket(config.server.replace(/^http/, 'ws') + '/ws?clientId=' + encodeURIComponent(config.client));
    socket.onmessage = event => {
      if (typeof event.data !== 'string') return;
      try {
        state = reduceProgress(state, JSON.parse(event.data), config);
        sessionStorage.setItem(config.prompt, JSON.stringify(state)); render();
      } catch (_) {}
    };
    socket.onopen = render;
    socket.onclose = () => { render(); };
    socket.onerror = () => { $('connection').textContent = 'Связь прервана; переподключение автоматически'; };
  }
  async function refresh() {
    if (busy) return;
    busy = true;
    try {
      const response = await fetch('/api');
      if (!response.ok) throw Error('HTTP ' + response.status);
      const next = await response.json();
      if (config.prompt !== next.prompt) {
        try { state = JSON.parse(sessionStorage.getItem(next.prompt) || '{}'); } catch (_) { state = {}; }
      }
      config = next;
      if (config.live) state = config.live;
      if (!config.samplers) config.samplers = Object.entries(config.labels || {}).filter(([id, label]) => /sampler/i.test(label) && !/select/i.test(label)).map(([id]) => id);
      render();
    } catch (_) { $('connection').textContent = 'Локальная страница недоступна; повторное подключение…'; }
    finally { busy = false; }
  }
  refresh(); setInterval(refresh, 2000);
}
