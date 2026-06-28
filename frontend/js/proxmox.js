/* ── Proxmox VM/CT status ───────────────────────────────────────
   VM/CT table with expandable rows and Start/Stop buttons.
*/

(function () {
  'use strict';

  let timer = null;

  async function fetchJSON(url, opts) {
    const r = await fetch(url, opts);
    if (!r.ok) throw new Error(r.status);
    return r.json();
  }

  function escapeHtml(v) {
    return String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }

  function statusBadge(status) {
    const running = String(status).toLowerCase().includes('run');
    const color = running ? 'var(--green)' : 'var(--red)';
    const text = running ? 'running' : (status || 'stopped');
    return `<span style="color:${color};font-weight:700">${escapeHtml(text)}</span>`;
  }

  function typeBadge(type) {
    const t = (type || 'vm').toLowerCase();
    const color = t === 'ct' ? 'var(--purple)' : 'var(--accent)';
    return `<span style="background:${color}22;color:${color};border:1px solid ${color}55;border-radius:6px;padding:1px 6px;font-size:10px;font-weight:700;text-transform:uppercase">${t}</span>`;
  }

  async function performAction(vmid, action, type) {
    if (!confirm(`${action} ${type.toUpperCase()} ${vmid} ausführen?`)) return;
    try {
      const r = await fetchJSON(`/api/proxmox/${action}/${vmid}`, { method: 'POST' });
      if (r.ok !== false) {
        setTimeout(refresh, 2000);
      } else {
        alert('Aktion fehlgeschlagen: ' + (r.detail || r.error || JSON.stringify(r)));
      }
    } catch (e) {
      alert('Aktion fehlgeschlagen: ' + e.message);
    }
  }

  async function refresh() {
    const tbody = document.getElementById('proxmox-tbody');
    const banner = document.getElementById('proxmox-errors');
    if (!tbody) return;
    tbody.innerHTML = '<tr><td colspan="7" class="loading">Lade VMs/CTs…</td></tr>';
    try {
      const data = await fetchJSON('/api/proxmox/vms');
      if (data.error && !(data.vms || []).length) {
        banner.style.display = 'flex';
        banner.textContent = `Proxmox konnte nicht geladen werden: ${data.error}`;
        tbody.innerHTML = '<tr><td colspan="7" class="loading">Keine Daten</td></tr>';
        return;
      }
      banner.style.display = 'none';
      const vms = data.vms || [];
      document.getElementById('proxmox-count').textContent = vms.length;

      tbody.innerHTML = vms.map(v => {
        const running = String(v.status).toLowerCase().includes('run');
        const startBtn = running
          ? `<button class="tab-btn" type="button" onclick="Proxmox.stop('${escapeHtml(v.vmid)}','${escapeHtml(v.type)}')" style="color:var(--red);border-color:var(--red)55">Stop</button>`
          : `<button class="tab-btn active" type="button" onclick="Proxmox.start('${escapeHtml(v.vmid)}','${escapeHtml(v.type)}')">Start</button>`;
        return `<tr data-vmid="${escapeHtml(v.vmid)}" style="cursor:pointer" onclick="Proxmox.toggleRow('${escapeHtml(v.vmid)}', this)">
          <td class="mono">${escapeHtml(v.vmid)}</td>
          <td><strong>${escapeHtml(v.name)}</strong></td>
          <td>${typeBadge(v.type)}</td>
          <td>${statusBadge(v.status)}</td>
          <td class="mono">${escapeHtml(v.cores || '—')}</td>
          <td class="mono">${escapeHtml(v.memory || '—')}</td>
          <td>${startBtn}</td>
        </tr>`;
      }).join('') || '<tr><td colspan="7" class="loading">Keine VMs/CTs gefunden</td></tr>';
    } catch (e) {
      banner.style.display = 'flex';
      banner.textContent = `Proxmox konnte nicht geladen werden: ${e.message}`;
      tbody.innerHTML = '<tr><td colspan="7" class="loading">Fehler</td></tr>';
    }
  }

  function toggleRow(vmid, tr) {
    const next = tr.nextElementSibling;
    if (next && next.classList.contains('proxmox-detail-row')) {
      next.remove();
      return;
    }
    document.querySelector('.proxmox-detail-row')?.remove();
    const row = document.createElement('tr');
    row.className = 'proxmox-detail-row';
    row.innerHTML = `<td colspan="7" style="padding:8px 12px;background:var(--card2,rgba(30,41,59,.78))">
      <div id="proxmox-detail-${vmid}" class="loading">Lade Details…</div>
    </td>`;
    tr.after(row);
    fetchJSON(`/api/proxmox/status/${vmid}`).then(d => {
      const el = document.getElementById(`proxmox-detail-${vmid}`);
      if (el) {
        el.innerHTML = `<pre style="white-space:pre-wrap;font-family:monospace;font-size:11px;color:var(--text)">${escapeHtml(d.raw || d.error || '—')}</pre>`;
      }
    }).catch(e => {
      const el = document.getElementById(`proxmox-detail-${vmid}`);
      if (el) el.textContent = 'Fehler: ' + e.message;
    });
  }

  window.Proxmox = {
    refresh,
    toggleRow,
    start: (vmid, type) => performAction(vmid, 'start', type),
    stop: (vmid, type) => performAction(vmid, 'stop', type),
  };

  function startTimer() {
    if (timer) clearInterval(timer);
    timer = setInterval(refresh, 60_000);
  }

  function init() {
    const btn = document.getElementById('proxmox-refresh');
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