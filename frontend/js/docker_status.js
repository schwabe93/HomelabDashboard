/* ── Docker container status (from Unraid) ─────────────────────
   Container table: name, image, status, CPU%, Memory, uptime, health.
   Refresh button + auto-refresh every 60s.
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

  function healthBadge(health) {
    if (!health) return '';
    const map = {
      healthy:    { color: 'var(--green)',  text: '✓ healthy' },
      unhealthy:  { color: 'var(--red)',    text: '✗ unhealthy' },
      starting:   { color: 'var(--yellow)', text: '… starting' },
      'no-healthcheck': { color: 'var(--muted)', text: '—' },
    };
    const m = map[health] || { color: 'var(--muted)', text: health };
    return ` <span style="color:${m.color};font-size:10px;font-weight:600">[${m.text}]</span>`;
  }

  function statusColor(container) {
    if (container.running) return 'var(--green)';
    return 'var(--red)';
  }

  async function fetchAndRender() {
    const tbody = document.getElementById('docker-tbody');
    const banner = document.getElementById('docker-errors');
    if (!tbody) return;
    tbody.innerHTML = '<tr><td colspan="7" class="loading">Lade Container…</td></tr>';
    try {
      const [statusRes, statsRes] = await Promise.all([
        fetchJSON('/api/docker/status'),
        fetchJSON('/api/docker/stats'),
      ]);
      if (statusRes.error && !statusRes.containers?.length) {
        banner.style.display = 'flex';
        banner.textContent = `Docker-Status konnte nicht geladen werden: ${statusRes.error}`;
        tbody.innerHTML = '<tr><td colspan="7" class="loading">Keine Daten</td></tr>';
        return;
      }
      banner.style.display = 'none';
      const statsMap = {};
      (statsRes.stats || []).forEach(s => { statsMap[s.name] = s; });
      const containers = statusRes.containers || [];
      document.getElementById('docker-count').textContent = containers.length;

      tbody.innerHTML = containers.map(c => {
        const s = statsMap[c.name] || {};
        const color = statusColor(c);
        return `<tr>
          <td><strong>${escapeHtml(c.name)}</strong></td>
          <td class="mono" style="font-size:11px;color:var(--muted)">${escapeHtml(c.image)}</td>
          <td style="color:${color};font-weight:600">${escapeHtml(c.status)}${healthBadge(c.health)}</td>
          <td class="mono">${escapeHtml(s.cpu || '—')}</td>
          <td class="mono">${escapeHtml(s.mem || '—')}</td>
          <td class="mono">${escapeHtml(c.uptime || '—')}</td>
          <td class="mono" style="font-size:10px;color:var(--muted)">${escapeHtml(c.ports || '')}</td>
        </tr>`;
      }).join('') || '<tr><td colspan="7" class="loading">Keine Container gefunden</td></tr>';
    } catch (e) {
      banner.style.display = 'flex';
      banner.textContent = `Docker-Status konnte nicht geladen werden: ${e.message}`;
      tbody.innerHTML = '<tr><td colspan="7" class="loading">Fehler</td></tr>';
    }
  }

  window.refreshDocker = fetchAndRender;

  function startTimer() {
    if (timer) clearInterval(timer);
    timer = setInterval(fetchAndRender, 60_000);
  }

  function init() {
    const btn = document.getElementById('docker-refresh');
    if (btn) btn.addEventListener('click', fetchAndRender);
    startTimer();
    fetchAndRender();
  }

  // Expose init so app.js can trigger when the view becomes active.
  window.DockerStatus = { init, refresh: fetchAndRender };
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();