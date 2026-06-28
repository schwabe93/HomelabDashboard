/* ──────────────────────────────────────────────────────────────
 * Starlink Outage Tracking – Frontend
 *
 * Zeigt:
 *   - Outage-Timeline (24h/7d) als visuelle Leiste (grün=online / rot=offline)
 *   - Uptime-Prozentsatz
 *   - Gesamtausfall, Anzahl Outages, längster Ausfall
 *   - Tabelle der letzten Outage-Ereignisse
 * ────────────────────────────────────────────────────────────── */

let outagesLoaded = false;
let currentOutagePeriod = '7d';

async function fetchJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(r.status);
  return r.json();
}

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function formatDuration(seconds) {
  if (!seconds || seconds <= 0) return '-';
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.round(seconds % 60);
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

function formatTs(ts) {
  return new Date(ts * 1000).toLocaleString('de-DE', {
    day: '2-digit', month: '2-digit', year: '2-digit',
    hour: '2-digit', minute: '2-digit',
  });
}

// ── Perioden-Switch ────────────────────────────────────────────
function setOutagePeriod(period, btn) {
  currentOutagePeriod = period;
  const group = btn?.closest('.tabs');
  group?.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  btn?.classList.add('active');
  refreshOutages();
}

// ── Daten laden & rendern ──────────────────────────────────────
async function refreshOutages() {
  try {
    const data = await fetchJSON(`/api/starlink/outages?period=${currentOutagePeriod}`);
    renderOutageStats(data);
    renderOutageTimeline(data);
    renderOutageTable(data);
  } catch (e) {
    console.warn('starlink/outages', e);
    const errEl = document.getElementById('outage-errors');
    if (errEl) { errEl.style.display = 'flex'; errEl.textContent = `Outage-Daten konnten nicht geladen werden: ${e.message}`; }
  }
}

function renderOutageStats(data) {
  const uptimeColor = data.uptime_pct >= 99 ? 'var(--green)' : data.uptime_pct >= 95 ? 'var(--yellow)' : 'var(--red)';
  const boxes = [
    [`${data.uptime_pct}%`, 'Uptime', uptimeColor],
    [formatDuration(data.total_downtime_s), 'Ausfall gesamt', 'var(--red)'],
    [String(data.outage_count), 'Outages', 'var(--accent)'],
    [formatDuration(data.longest_outage_s), 'Längster Ausfall', 'var(--yellow)'],
  ];
  const el = document.getElementById('outage-stats');
  if (el) el.innerHTML = boxes.map(([v, l, c]) =>
    `<div class="stat-box"><div class="big-num" style="color:${c}">${escapeHtml(v)}</div><div class="big-label">${escapeHtml(l)}</div></div>`
  ).join('');
}

function renderOutageTimeline(data) {
  const container = document.getElementById('outage-timeline');
  if (!container) return;
  const events = data.events || [];
  if (!events.length) {
    container.innerHTML = '<div style="color:var(--muted);text-align:center;padding:20px">Keine Outage-Daten im Zeitraum</div>';
    return;
  }

  const now = Math.floor(Date.now() / 1000);
  const periodSecs = currentOutagePeriod === '24h' ? 86400 : 604800;
  const start = now - periodSecs;

  // Segmente aus Events konstruieren
  // Jedes Event markiert den Beginn eines Zustands.
  const segments = [];
  for (let i = 0; i < events.length; i++) {
    const ev = events[i];
    const segStart = Math.max(ev.timestamp, start);
    const segEnd = i + 1 < events.length ? events[i + 1].timestamp : now;
    const segEndClamped = Math.min(segEnd, now);
    if (segEndClamped <= segStart) continue;
    segments.push({ start: segStart, end: segEndClamped, state: ev.event });
  }
  // Falls der erste Event später als Start ist: Lücke als "unbekannt" auffüllen
  if (segments.length && segments[0].start > start) {
    segments.unshift({ start, end: segments[0].start, state: 'unknown' });
  }
  // Falls gar keine Segmente: ganze Leiste als unbekannt
  if (!segments.length) {
    segments.push({ start, end: now, state: 'unknown' });
  }

  // HTML-Segmente als proportionale Leiste
  let html = '<div class="outage-bar">';
  segments.forEach(seg => {
    const width = Math.max(0.2, (seg.end - seg.start) / periodSecs * 100);
    const cls = seg.state === 'online' ? 'seg-online' : seg.state === 'offline' ? 'seg-offline' : 'seg-unknown';
    const title = `${formatTs(seg.start)} – ${formatTs(seg.end)} (${seg.state})`;
    html += `<div class="outage-seg ${cls}" style="width:${width}%" title="${escapeHtml(title)}"></div>`;
  });
  html += '</div>';

  // Zeitskala
  const ticks = 6;
  let scale = '<div class="outage-scale">';
  for (let i = 0; i <= ticks; i++) {
    const t = start + (periodSecs / ticks) * i;
    scale += `<span>${new Date(t * 1000).toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit' })}${currentOutagePeriod === '24h' ? ' ' + new Date(t*1000).toLocaleTimeString('de-DE',{hour:'2-digit',minute:'2-digit'}) : ''}</span>`;
  }
  scale += '</div>';

  // Legende
  const legend = '<div class="outage-legend"><span class="leg-item"><span class="leg-dot leg-online"></span>Online</span><span class="leg-item"><span class="leg-dot leg-offline"></span>Offline</span><span class="leg-item"><span class="leg-dot leg-unknown"></span>Unbekannt</span></div>';

  container.innerHTML = html + scale + legend;
}

function renderOutageTable(data) {
  const tbody = document.getElementById('outage-events-tbody');
  if (!tbody) return;
  const events = (data.events || []).slice().reverse(); // neueste zuerst
  if (!events.length) {
    tbody.innerHTML = '<tr><td colspan="5" class="loading">Keine Ereignisse</td></tr>';
    return;
  }
  tbody.innerHTML = events.map(ev => {
    const isOffline = ev.event === 'offline';
    const stateColor = isOffline ? 'var(--red)' : 'var(--green)';
    const stateIcon = isOffline ? '🔴' : '🟢';
    return `
      <tr>
        <td>${stateIcon} <span style="color:${stateColor}">${escapeHtml(ev.event)}</span></td>
        <td class="mono">${formatTs(ev.timestamp)}</td>
        <td>${ev.duration_s != null && ev.duration_s > 0 ? formatDuration(ev.duration_s) : '—'}</td>
        <td class="mono">${ev.latency_ms != null ? ev.latency_ms + ' ms' : '—'}</td>
        <td>${escapeHtml(ev.event === 'offline' ? 'Ausfall begonnen' : 'Verbindung wiederhergestellt')}</td>
      </tr>
    `;
  }).join('');
}

// ── Init beim View-Wechsel ─────────────────────────────────────
async function initOutagesView() {
  if (!outagesLoaded) {
    outagesLoaded = true;
    document.querySelectorAll('[data-outage-period]').forEach(btn => {
      btn.addEventListener('click', () => setOutagePeriod(btn.dataset.outagePeriod, btn));
    });
  }
  await refreshOutages();
}

let outagesTimer = null;
function startOutagesTimer() {
  if (outagesTimer) return;
  outagesTimer = setInterval(() => { if (currentView === 'starlink') refreshOutages(); }, 60_000);
}

// Globale Referenzen für app.js
window.initOutagesView = initOutagesView;
window.startOutagesTimer = startOutagesTimer;

window.addEventListener('load', () => {
  document.querySelectorAll('[data-outage-period]').forEach(btn => {
    if (btn.dataset.outagePeriod === currentOutagePeriod) btn.classList.add('active');
  });
  startOutagesTimer();
});