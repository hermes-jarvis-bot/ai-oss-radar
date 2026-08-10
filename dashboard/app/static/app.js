const state = { repos: [], all: [], watch: [], pins: [] };
let historyChart = null;
let activeHistoryRepo = null;
const translations = {
  ru: { refresh: 'Обновить экран', topToday: 'Top сегодня', accelerating: 'Ускоряются', top: 'Top', pinnedTab: 'Мои', history: 'История', candidates: 'Кандидаты', candidatesNote: 'Ранжирование из последнего отчёта.', filter: 'Поиск репозитория', watchNote: 'Автоматические кандидаты и ваши ручные закрепления.', days: 'дней', pinAdd: '+ Закрепить', pinnedTitle: 'Мои закреплённые', pinnedNote: 'Постоянно наблюдаемые проекты без 14-day срока.', historyCandidate: 'История кандидата', historySelect: 'Выберите репозиторий в разделе Top.', footer: 'Потяните страницу вниз, чтобы обновить локальные данные. GitHub collection выполняется по расписанию. · SQLite history локальна.', loading: 'Загрузка телеметрии…', noDescription: 'Описание отсутствует', aiTooling: 'AI-инструменты', noResults: 'Ничего не найдено.', pin: '☆ Закрепить', pinned: '★ Закреплено', manualPin: 'ручное закрепление', noExpiry: 'без срока', until: 'до', watchEmpty: 'Watchlist появится после ближайшего collection run.', pendingSnapshot: 'Описание и метрики появятся после ближайшего collection run.', snapshotWaiting: 'ожидает snapshot', pinnedEmpty: 'Пока нет ручных закреплений. Добавьте owner/repository во вкладке Watchlist.', pinRemoved: 'ручное закрепление снято.', pinAdded: 'закреплён для ежедневного наблюдения.', noSnapshots: 'Нет снимков — дождитесь первого collection run.', noData: 'нет данных', urgent: 'истекают ≤3 дней:', noUrgent: 'срочных истечений нет', status: 'Данные:', schedule: 'GitHub collection — ежедневно в 11:00 Алматы', observations: 'наблюдений', lastSnapshot: 'последний снимок:', openGithub: 'Открыть GitHub ↗', projectHistory: 'ИСТОРИЯ ПРОЕКТА', fault: 'Сбой', chartAria: 'График роста stars', stars: 'Stars', snapshot: 'Снимок', dailyChange: 'Изменение за день', latestValue: 'Последнее собранное значение', tapPoint: 'Нажмите точку, чтобы изучить snapshot', baseline: 'Базовый снимок', selectedSnapshot: 'Выбранный снимок', changeSincePrevious: 'изменение с прошлого снимка', now: 'СЕЙЧАС' },
  en: { refresh: 'Refresh screen', topToday: 'Top today', accelerating: 'Accelerating', top: 'Top', pinnedTab: 'Pinned', history: 'History', candidates: 'Candidates', candidatesNote: 'Ranking from the latest report.', filter: 'Search repositories', watchNote: 'Automatic candidates and your manual pins.', days: 'days', pinAdd: '+ Pin', pinnedTitle: 'My pinned projects', pinnedNote: 'Projects monitored indefinitely, without a 14-day expiry.', historyCandidate: 'Candidate history', historySelect: 'Choose a repository from Top.', footer: 'Pull down to refresh local data. GitHub collection runs on schedule. · SQLite history is local.', loading: 'Loading telemetry…', noDescription: 'No description available', aiTooling: 'AI tooling', noResults: 'No repositories found.', pin: '☆ Pin', pinned: '★ Pinned', manualPin: 'manual pin', noExpiry: 'no expiry', until: 'until', watchEmpty: 'The watchlist will appear after the next collection run.', pendingSnapshot: 'Description and metrics will appear after the next collection run.', snapshotWaiting: 'awaiting snapshot', pinnedEmpty: 'No manual pins yet. Add owner/repository in Watchlist.', pinRemoved: 'manual pin removed.', pinAdded: 'pinned for daily observation.', noSnapshots: 'No snapshots yet — wait for the first collection run.', noData: 'no data', urgent: 'expiring in ≤3 days:', noUrgent: 'no urgent expiries', status: 'Data:', schedule: 'GitHub collection — daily at 11:00 Almaty', observations: 'observations', lastSnapshot: 'latest snapshot:', openGithub: 'Open GitHub ↗', projectHistory: 'PROJECT HISTORY', fault: 'Fault', chartAria: 'Star growth chart', stars: 'Stars', snapshot: 'Snapshot', dailyChange: 'Daily change', latestValue: 'Latest collected value', tapPoint: 'Tap a point to inspect this snapshot', baseline: 'Baseline snapshot', selectedSnapshot: 'Selected snapshot', changeSincePrevious: 'change since previous snapshot', now: 'NOW' },
};
const requestedLanguage = new URLSearchParams(location.search).get('lang');
let language = requestedLanguage === 'en' || requestedLanguage === 'ru' ? requestedLanguage : (localStorage.getItem('radar-language') === 'en' ? 'en' : 'ru');
const requestedTheme = new URLSearchParams(location.search).get('theme');
let theme = ['system', 'light', 'dark'].includes(requestedTheme) ? requestedTheme : (localStorage.getItem('radar-theme') || 'system');
const systemTheme = window.matchMedia('(prefers-color-scheme: light)');
const t = key => translations[language][key] || key;
const fmt = n => n == null ? 'N/A' : new Intl.NumberFormat(language === 'ru' ? 'ru-RU' : 'en-US').format(n);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
const date = value => value ? new Date(value).toLocaleDateString(language === 'ru' ? 'ru-RU' : 'en-US') : '—';
const github = item => item.html_url || item.url || `https://github.com/${item.full_name || item.repo}`;

function applyLanguage() {
  document.documentElement.lang = language;
  document.querySelectorAll('.language-button').forEach(button => {
    const active = button.dataset.language === language;
    button.classList.toggle('active', active);
    button.setAttribute('aria-pressed', String(active));
  });
  document.querySelectorAll('[data-i18n]').forEach(node => { node.textContent = t(node.dataset.i18n); });
  const filter = document.querySelector('#filter');
  filter.placeholder = t('filter'); filter.setAttribute('aria-label', t('filter'));
  document.querySelector('#status').textContent = t('loading');
}

function effectiveTheme() { return theme === 'system' ? (systemTheme.matches ? 'light' : 'dark') : theme; }
function applyTheme() {
  const active = effectiveTheme();
  document.documentElement.dataset.theme = active;
  const button = document.querySelector('#theme-toggle');
  button.textContent = theme === 'system' ? 'A' : (active === 'dark' ? '☾' : '☀︎');
  const stateName = language === 'ru' ? ({ system: 'авто', light: 'светлая', dark: 'тёмная' }[theme]) : ({ system: 'auto', light: 'light', dark: 'dark' }[theme]);
  button.setAttribute('aria-label', language === 'ru' ? `Тема: ${stateName}` : `Theme: ${stateName}`);
  button.title = language === 'ru' ? `Тема: ${stateName}` : `Theme: ${stateName}`;
  if (activeHistoryRepo) showHistory(activeHistoryRepo).catch(() => {});
}

async function api(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || response.statusText);
  return response.json();
}

function setView(name, updateLocation = true) {
  document.querySelectorAll('.tab').forEach(x => x.classList.toggle('active', x.dataset.view === name));
  document.querySelectorAll('.view').forEach(x => x.classList.toggle('active', x.id === `${name}-view`));
  if (updateLocation) history.replaceState(null, '', `#${name}`);
}

function pinButton(name) {
  const pinned = state.pins.some(x => x.toLowerCase() === name.toLowerCase());
  return `<button class="pin-toggle" data-pin="${esc(name)}">${t(pinned ? 'pinned' : 'pin')}</button>`;
}

function renderCandidates() {
  const query = document.querySelector('#filter').value.toLowerCase();
  const items = state.repos.filter(x => x.full_name.toLowerCase().includes(query));
  document.querySelector('#candidates').innerHTML = items.map((x, i) => `<article class="candidate" data-repo="${esc(x.full_name)}"><div class="rank">#${i + 1}</div><div class="candidate-main"><a href="${esc(github(x))}" target="_blank" rel="noreferrer noopener">${esc(x.full_name)} ↗</a><p>${esc(x.description || t('noDescription'))}</p><div class="tags"><span>${esc(x.category || x.language || t('aiTooling'))}</span><span class="state ${esc(x.trend_state || 'bootstrap').toLowerCase()}">${esc(x.trend_state || 'BOOTSTRAP')}</span></div></div><div class="numbers"><b>${fmt(x.stars)}</b><small>stars</small><strong class="delta">${x.stars_24h == null ? 'N/A' : '+' + fmt(x.stars_24h)}</strong><small>24h</small>${pinButton(x.full_name)}</div></article>`).join('') || `<p class="empty">${t('noResults')}</p>`;
  bindInteractiveCards('#candidates');
}

function renderWatch() {
  document.querySelector('#watchlist').innerHTML = state.watch.length ? state.watch.map(x => `<article><div><a href="${esc(github(x))}" target="_blank" rel="noreferrer noopener">${esc(x.full_name)} ↗</a><span>${x.manual ? t('manualPin') : esc(x.reason || 'watchlist')}</span></div><div><strong>${fmt(x.stars)}</strong><small>${x.manual ? t('noExpiry') : `${t('until')} ${date(x.expires_at)}`}</small>${pinButton(x.full_name)}</div></article>`).join('') : `<p class="empty">${t('watchEmpty')}</p>`;
  bindInteractiveCards('#watchlist');
}

function renderPinned() {
  const indexed = new Map(state.watch.map(x => [x.full_name.toLowerCase(), x]));
  const items = state.pins.map(name => indexed.get(name.toLowerCase()) || { full_name: name, manual: true });
  document.querySelector('#pinned-list').innerHTML = items.map(x => `<article class="candidate pinned-card"><div class="candidate-main"><a href="${esc(github(x))}" target="_blank" rel="noreferrer noopener">${esc(x.full_name)} ↗</a><p>${esc(x.description || t('pendingSnapshot'))}</p><div class="tags"><span>${t('manualPin')}</span><span>${x.stars == null ? t('snapshotWaiting') : `${fmt(x.stars)} stars`}</span></div></div><div class="numbers">${pinButton(x.full_name)}</div></article>`).join('') || `<p class="empty">${t('pinnedEmpty')}</p>`;
  bindInteractiveCards('#pinned-list');
}

function bindInteractiveCards(selector) {
  document.querySelectorAll(`${selector} [data-pin]`).forEach(button => button.onclick = event => { event.stopPropagation(); togglePin(button.dataset.pin); });
  document.querySelectorAll(`${selector} [data-repo]`).forEach(card => card.onclick = event => { if (event.target.closest('a,button')) return; showHistory(card.dataset.repo); });
}

async function togglePin(fullName) {
  const pinned = state.pins.some(x => x.toLowerCase() === fullName.toLowerCase());
  await api(pinned ? `/api/manual-watchlist/${encodeURIComponent(fullName)}` : '/api/manual-watchlist', pinned ? { method: 'DELETE' } : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ full_name: fullName }) });
  document.querySelector('#pin-status').textContent = `${fullName}: ${t(pinned ? 'pinRemoved' : 'pinAdded')}`;
  await load();
}

async function showHistory(repo) {
  activeHistoryRepo = repo;
  setView('history');
  const payload = await api(`/api/repositories/${encodeURIComponent(repo)}/history`);
  const item = payload.summary;
  const history = payload.history;
  const values = history.map(x => x.stars);
  const labels = history.map(x => date(x.ts));
  const tooltipDate = value => new Date(value).toLocaleString(language === 'ru' ? 'ru-RU' : 'en-US');
  const css = getComputedStyle(document.documentElement);
  const accent = css.getPropertyValue('--accent').trim();
  const muted = css.getPropertyValue('--muted').trim();
  const line = css.getPropertyValue('--line').trim();
  const panel = css.getPropertyValue('--panel').trim();
  const chartHost = document.querySelector('#chart');
  const chartSelection = document.querySelector('#chart-selection');
  if (historyChart) historyChart.destroy();
  chartHost.innerHTML = '<canvas></canvas>';
  chartHost.setAttribute('aria-label', t('chartAria'));
  chartSelection.textContent = t('tapPoint');
  const latestDelta = values.length > 1 ? values.at(-1) - values.at(-2) : 0;
  const latestLabel = {
    id: 'latestSnapshotLabel',
    afterDatasetsDraw(chart) {
      const point = chart.getDatasetMeta(0).data.at(-1);
      if (!point) return;
      const { ctx, chartArea } = chart;
      const label = `${t('now')}  ${fmt(values.at(-1))} · +${fmt(latestDelta)} / 24h`;
      ctx.save();
      ctx.font = '700 12px system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif';
      const width = ctx.measureText(label).width + 18;
      const x = Math.max(chartArea.left, point.x - width - 10);
      const y = Math.max(chartArea.top + 10, point.y - 34);
      ctx.fillStyle = panel;
      ctx.strokeStyle = accent;
      ctx.lineWidth = 1;
      ctx.beginPath();
      if (ctx.roundRect) ctx.roundRect(x, y, width, 25, 7); else ctx.rect(x, y, width, 25);
      ctx.fill(); ctx.stroke();
      ctx.fillStyle = effectiveTheme() === 'light' ? '#16283b' : '#e5eef8';
      ctx.fillText(label, x + 9, y + 16);
      ctx.restore();
    },
  };
  historyChart = new Chart(chartHost.querySelector('canvas'), {
    type: 'line',
    data: {
      labels,
      datasets: [{
        label: t('stars'), data: values, borderColor: accent, borderWidth: 3,
        backgroundColor: context => {
          const { chart } = context;
          const { ctx, chartArea } = chart;
          if (!chartArea) return accent;
          const gradient = ctx.createLinearGradient(0, chartArea.top, 0, chartArea.bottom);
          gradient.addColorStop(0, `${accent}44`); gradient.addColorStop(1, `${accent}00`);
          return gradient;
        },
        fill: true, tension: .32, pointRadius: 0, pointHoverRadius: 6,
        pointHoverBackgroundColor: '#fcd34d', pointHoverBorderColor: accent,
      }],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false, axis: 'x' },
      plugins: {
        legend: { display: false },
        tooltip: {
          displayColors: false, backgroundColor: panel, borderColor: accent, borderWidth: 1,
          cornerRadius: 9, padding: 12,
          titleFont: { family: 'system-ui', weight: '700' }, bodyFont: { family: 'system-ui' },
          callbacks: {
            title: items => `${t('snapshot')} · ${tooltipDate(history[items[0].dataIndex].ts)}`,
            label: item => `${t('stars')}: ${fmt(item.parsed.y)}`,
            afterLabel: item => {
              const index = item.dataIndex;
              if (!index) return t('baseline');
              const delta = values[index] - values[index - 1];
              const growth = ((delta / values[index - 1]) * 100).toFixed(1);
              return `${t('dailyChange')}: +${fmt(delta)} (${growth}%)`;
            },
            footer: items => items[0].dataIndex === values.length - 1 ? t('latestValue') : t('tapPoint'),
          },
        },
      },
      scales: {
        x: { grid: { display: false }, ticks: { color: muted, maxTicksLimit: 4, font: { family: 'system-ui' } } },
        y: { grid: { color: line }, ticks: { color: muted, font: { family: 'system-ui' }, callback: value => fmt(value) } },
      },
      onClick: (_, elements) => {
        if (!elements.length) return;
        const index = elements[0].index;
        const delta = index ? values[index] - values[index - 1] : null;
        chartSelection.textContent = `${t('selectedSnapshot')} · ${tooltipDate(history[index].ts)} · ${t('stars')}: ${fmt(values[index])}${delta == null ? ` · ${t('baseline')}` : ` · ${t('changeSincePrevious')}: +${fmt(delta)}`}`;
      },
    },
    plugins: [latestLabel],
  });
  document.querySelector('#history-summary').innerHTML = `<div><p class="eyebrow">${t('projectHistory')}</p><h2>${esc(item.full_name)}</h2><p>${esc(item.description || t('noDescription'))}</p><p id="history-note" class="history-note"></p><div class="tags"><span>${esc(item.language || '—')}</span><span>${fmt(item.stars)} stars</span><span>${t('lastSnapshot')} ${date(item.ts)}</span></div></div><div class="history-actions"><a href="${esc(github(item))}" target="_blank" rel="noreferrer noopener">${t('openGithub')}</a>${pinButton(item.full_name)}</div>`;
  document.querySelector('#history-note').textContent = `${history.length} ${t('observations')} · ${date(history[0].ts)} — ${date(history.at(-1).ts)}`;
  bindInteractiveCards('#history-summary');
  setView('history');
}

async function load() {
  try {
    const [health, summary, all, watch, pins] = await Promise.all([api('/health'), api('/api/summary'), api('/api/repositories'), api('/api/watchlist'), api('/api/manual-watchlist')]);
    state.repos = summary.repositories; state.all = all; state.watch = watch; state.pins = pins.repositories;
    if (!health.latest_snapshot) {
      document.querySelector('#status').textContent = t('noSnapshots');
      ['#repos', '#accelerating', '#watchcount'].forEach(x => document.querySelector(x).textContent = '0');
      document.querySelector('#expiring').textContent = t('noData'); renderCandidates(); renderWatch(); renderPinned(); return;
    }
    const accelerated = state.repos.filter(x => x.trend_state === 'ACCELERATING').length;
    const soon = watch.filter(x => { const remaining = new Date(x.expires_at) - Date.now(); return !x.manual && remaining >= 0 && remaining < 3 * 864e5; }).length;
    document.querySelector('#status').textContent = `${t('status')} ${new Date(health.latest_snapshot).toLocaleString(language === 'ru' ? 'ru-RU' : 'en-US')} · ${t('schedule')}`;
    document.querySelector('#repos').textContent = fmt(state.repos.length); document.querySelector('#accelerating').textContent = fmt(accelerated); document.querySelector('#watchcount').textContent = fmt(watch.length); document.querySelector('#expiring').textContent = soon ? `${t('urgent')} ${soon}` : t('noUrgent');
    renderCandidates(); renderWatch(); renderPinned();
  } catch (error) { document.querySelector('#status').textContent = `${t('fault')}: ${error.message}`; }
}

document.querySelector('#filter').oninput = renderCandidates;
document.querySelector('#pin-form').onsubmit = async event => { event.preventDefault(); const input = document.querySelector('#pin-input'); try { await togglePin(input.value.trim()); input.value = ''; } catch (error) { document.querySelector('#pin-status').textContent = `${t('fault')}: ${error.message}`; } };
document.querySelectorAll('.tab').forEach(tab => tab.onclick = () => { setView(tab.dataset.view); load(); });
document.querySelectorAll('.language-button').forEach(button => button.onclick = () => { language = button.dataset.language; localStorage.setItem('radar-language', language); applyLanguage(); applyTheme(); load(); });
document.querySelector('#theme-toggle').onclick = () => { theme = ({ system: 'light', light: 'dark', dark: 'system' })[theme]; localStorage.setItem('radar-theme', theme); applyTheme(); };
systemTheme.addEventListener('change', () => { if (theme === 'system') applyTheme(); });
let pullStart = 0;
document.addEventListener('touchstart', event => { if (window.scrollY === 0) pullStart = event.touches[0].clientY; }, { passive: true });
document.addEventListener('touchend', event => { if (pullStart && event.changedTouches[0].clientY - pullStart > 80) load(); pullStart = 0; }, { passive: true });
const initialView = location.hash.slice(1);
if (['candidates', 'watch', 'pinned', 'history'].includes(initialView)) setView(initialView, false);
applyLanguage();
applyTheme();
load();
