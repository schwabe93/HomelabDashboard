/* ── Uptime Kuma integration ───────────────────────────────────
   Monitor cards/grid with status dot, uptime %, response time.
   Summary: total monitors, up count, down count.
   Auto-refresh every 60s.
*/

(function () {
  'use strict';

  let timer = null;

  async function fetchJSON(url) {
    const r = await fetch(url);
    if (!r.ok) throw new Error(r.status);
    return r.json();
  }

  function escapeHtml(v) {
    return String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }

  function statusDot(status) {
    const color = status === 'up' ? 'var(--green)' : 'var(--red)';
    return `<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${color};box-shadow:0 0 6px ${color}"></span>`;
  }

  function fmtResponseTime(ms) {
    if (ms == null) return '—';
    const n = Number(ms);
    if (!isFinite(n)) return escapeHtml(ms);
    if (n < 1000) return `${n} ms`;
    return `${(n / 1000).toFixed(2)} s`;
  }

  function fmtTime(ts) {
    if (!ts) return '—';
    const d = new Date(ts);
    if (isNaN(d.getTime())) return escapeHtml(ts);
    return d.toLocaleString('de-DE');
  }

  async function refresh() {
    const grid = document.getElementById('uptime-kuma-grid');
    const summary = document.getElementById('uptime-kuma-summary');
    const banner = document.getElementById('uptime-kuma-errors');
    if (!grid) return;
    grid.innerHTML = '<div class="loading">Lade Monitore…</div>';
    try {
      const data = await fetchJSON('/api/uptime-kuma/status');
      if (data.error && !(data.monitors || []).length) {
        banner.style.display = 'flex';
        banner.textContent = `Uptime Kuma: ${data.error}`;
        grid.innerHTML = '<div style="color:var(--muted);padding:20px;text-align:center">Keine Monitore verfügbar</div>';
        if (summary) summary.innerHTML = '';
        return;
      }
      banner.style.display = 'none';
      const monitors = data.monitors || [];
      const s = data.summary || { total: monitors.length, up: 0, down: 0 };
      if (summary) {
        summary.innerHTML = `
          <div class="stat-box"><div class="big-num">${s.total}</div><div class="big-label">Monitore</div></div>
          <div class="stat-box"><div class="big-num" style="color:var(--green)">${s.up}</div><div class="big-label">Online</div></div>
          <div class="stat-box"><div class="big-num" style="color:var(--red)">${s.down}</div><div class="big-label">Offline</div></div>`;
      }

      grid.innerHTML = monitors.map(m => `
        <div class="card" style="min-width:0">
          <div class="card-header" style="justify-content:flex-start;gap:8px">
            ${statusDot(m.status)}
            <span style="color:var(--text);text-transform:none;letter-spacing:0;font-size:12px;font-weight:700">${escapeHtml(m.name)}</span>
          </div>
          <div class="card-body">
            <div class="stat-row">
              <div class="stat-box">
                <div class="big-num" style="color:${m.uptime_pct >= 99 ? 'var(--green)' : m.uptime_pct >= 90 ? 'var(--yellow)' : 'var(--red)'}">${m.uptime_pct}%</div>
                <div class="big-label">Uptime</div>
              </div>
              <div class="stat-box">
                <div class="big-num" style="color:var(--accent)">${fmtResponseTime(m.response_time)}</div>
                <div class="big-label">Antwortzeit</div>
              </div>
            </div>
            <div style="font-size:10px;color:var(--muted);margin-top:6px">Letzte Prüfung: ${fmtTime(m.last_check)}</div>
            ${m.msg ? `<div style="font-size:10px;color:var(--muted);margin-top:4px">${escapeHtml(m.msg)}</div>` : ''}
          </div>
        </div>`).join('') || '<div style="color:var(--muted);padding:20px;text-align:center">Keine Monitore gefunden</div>';
    } catch (e) {
      banner.style.display = 'flex';
      banner.textContent = `Uptime Kuma konnte nicht geladen werden: ${e.message}`;
      grid.innerHTML = '';
    }
  }

  window.UptimeKuma = { refresh };

  function startTimer() {
    if (timer) clearInterval(timer);
    timer = setInterval(refresh, 60_000);
  }

  function init() {
    const btn = document.getElementById('uptime-kuma-refresh');
    if (btn) btn.addEventListener('click', refresh);
    startTimer();
    refresh();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();