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
  const I18N = {
    en: {
      locale: 'en-GB',
      pageTitle: 'Generation progress',
      segment: n => `Segment ${n}`,
      step: (v, m) => `Step ${v} of ${m}`,
      noSteps: 'Waiting for step data from ComfyUI',
      eta: (left, at) => `≈ ${left} left · finish ≈ ${at}`,
      span: (m, s) => m ? `${m} min ${s} s` : `${s} s`,
      footnote: 'The percentage refers to sampling steps, not to the whole generation. Decoding and saving follow the last step.',
      review: 'Ready to review',
      failed: 'Generation failed',
      rejected: 'Waiting for a new version',
      decoding: 'Decoding / saving',
      sampling: 'Sampling',
      preparing: 'Preparing / waiting for sampling',
      idle: 'Waiting to start',
      decodeLabel: 'Decoding',
      saveLabel: 'Saving video',
      doneDetail: 'Video created. Review happens in the chat.',
      failedDetail: 'Generation stopped. There is no automatic restart.',
      connected: 'Connected · updates automatically',
      saved: 'Result saved',
      connecting: 'Connecting to ComfyUI events…',
      noLink: 'No connection to ComfyUI',
      broken: 'Connection lost; reconnecting automatically',
      local: 'Local page unavailable; reconnecting…'
    },
    ru: {
      locale: 'ru-RU',
      pageTitle: 'Прогресс генерации',
      segment: n => `Фрагмент ${n}`,
      step: (v, m) => `Шаг ${v} из ${m}`,
      noSteps: 'Ждём данные о шагах от ComfyUI',
      eta: (left, at) => `Осталось ≈ ${left} · финиш ≈ ${at}`,
      span: (m, s) => m ? `${m} мин ${s} с` : `${s} с`,
      footnote: 'Процент относится к шагам расчёта, а не ко всему времени генерации. После расчёта выполняются декодирование и сохранение.',
      review: 'Готово к просмотру',
      failed: 'Ошибка генерации',
      rejected: 'Ожидание новой версии',
      decoding: 'Декодирование / сохранение',
      sampling: 'Расчёт шагов',
      preparing: 'Подготовка / ожидание расчёта',
      idle: 'Ожидание запуска',
      decodeLabel: 'Декодирование',
      saveLabel: 'Сохранение видео',
      doneDetail: 'Видео создано. Оценка результата — в чате.',
      failedDetail: 'Генерация остановлена. Автоматического перезапуска нет.',
      connected: 'Подключено · обновляется автоматически',
      saved: 'Результат сохранён',
      connecting: 'Подключение к событиям ComfyUI…',
      noLink: 'Нет связи с ComfyUI',
      broken: 'Связь прервана; переподключение автоматически',
      local: 'Локальная страница недоступна; повторное подключение…'
    }
  };
  const $ = id => document.getElementById(id);
  const forced = (new URLSearchParams(location.search).get('lang') || '').toLowerCase();
  let config = {}, state = {}, socket, socketClient, busy = false;
  const timing = {value: null, at: null, perStep: null, decode: 32};

  function pickLang(tag) {
    const raw = (forced || tag || window.FILM_LANG || 'en').toLowerCase();
    return raw.startsWith('ru') ? 'ru' : 'en';
  }
  let lang = pickLang(), L = I18N[lang];

  function applyLang(tag) {
    const next = pickLang(tag);
    if (next === lang) return;
    lang = next; L = I18N[lang];
    document.documentElement.lang = lang;
    document.title = L.pageTitle;
    render();
  }

  function clock(sec) {
    const t = new Date(Date.now() + sec * 1000);
    return t.toLocaleTimeString(L.locale, {hour: '2-digit', minute: '2-digit', second: '2-digit'});
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
    return L.eta(L.span(m, s), clock(left));
  }
  function render() {
    document.documentElement.lang = lang;
    document.title = L.pageTitle;
    $('footnote').textContent = L.footnote;
    $('title').textContent = config.title || 'ComfyUI';
    $('segment').textContent = config.segment ? L.segment(config.segment) : '';
    const done = ['review', 'accepted'].includes(config.status);
    const failed = config.status === 'failed' || state.error;
    if (state.max) {
      const percent = Math.min(100, Math.round(state.value / state.max * 100));
      $('percent').textContent = percent + '%'; $('bar').value = percent;
      $('detail').textContent = L.step(state.value, state.max);
    } else {
      $('percent').textContent = '—'; $('bar').removeAttribute('value');
      $('detail').textContent = L.noSteps;
    }
    timing.value = state.max ? state.value : null;
    $('eta').textContent = etaText();
    const label = config.labels?.[state.node] || state.node || '';
    $('phase').textContent = done ? L.review : failed ? L.failed :
      config.status === 'rejected' ? L.rejected :
      config.status === 'running' ? (state.max && state.value >= state.max ? L.decoding : state.max ? L.sampling : L.preparing) : L.idle;
    if (!done && !failed && /decode/i.test(label)) $('phase').textContent = L.decodeLabel;
    if (!done && !failed && /save|createvideo/i.test(label)) $('phase').textContent = L.saveLabel;
    if (done) {
      $('percent').textContent = '100%'; $('bar').value = 100;
      $('detail').textContent = L.doneDetail;
    }
    if (failed) $('detail').textContent = L.failedDetail;
    $('connection').textContent = config.connection_warning ? L.noLink :
      (config.live?.connected ? L.connected : done ? L.saved : L.connecting);
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
    socket.onerror = () => { $('connection').textContent = L.broken; };
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
      applyLang(next.lang);
      if (config.live) state = config.live;
      if (!config.samplers) config.samplers = Object.entries(config.labels || {}).filter(([id, label]) => /sampler/i.test(label) && !/select/i.test(label)).map(([id]) => id);
      render();
    } catch (_) { $('connection').textContent = L.local; }
    finally { busy = false; }
  }
  render(); refresh(); setInterval(refresh, 2000);
}
