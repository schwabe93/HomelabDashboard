// ── Port Forwarding / NAT Rules ────────────────────────────────────
// Depends on: fetchJSON, escapeHtml

let natRules = [];
let natFilter = '';

async function refreshNatRules() {
  const body = document.getElementById('nat-rules-body');
  if (!body) return;
  body.innerHTML = '<div class="loading">Lade Port-Forwarding-Regeln…</div>';
  try {
    natRules = await fetchJSON('/api/nat/rules');
    renderNatRules();
  } catch (e) {
    body.innerHTML = `<div class="loading" style="color:var(--red)">Fehler beim Laden: ${escapeHtml(e.message)}</div>`;
  }
}

function renderNatRules() {
  const body = document.getElementById('nat-rules-body');
  const countEl = document.getElementById('nat-count');
  if (!body) return;

  let filtered = natRules;
  if (natFilter) {
    const f = natFilter.toLowerCase();
    filtered = natRules.filter(r =>
      (r.protocol || '').toLowerCase().includes(f) ||
      (r.source || '').toLowerCase().includes(f) ||
      (r.destination || '').toLowerCase().includes(f) ||
      (r.port || '').toLowerCase().includes(f) ||
      (r.target || '').toLowerCase().includes(f) ||
      (r.description || '').toLowerCase().includes(f) ||
      (r.interface || '').toLowerCase().includes(f)
    );
  }

  if (countEl) countEl.textContent = `${filtered.length} / ${natRules.length}`;

  if (!filtered.length) {
    body.innerHTML = '<div class="loading">Keine Port-Forwarding-Regeln gefunden.</div>';
    return;
  }

  const tbody = document.getElementById('nat-rules-tbody');
  if (!tbody) return;
  tbody.innerHTML = filtered.map(r => {
    const statusColor = r.enabled ? 'var(--green)' : 'var(--muted)';
    const statusBg = r.enabled ? 'rgba(34,197,94,.15)' : 'rgba(148,163,184,.10)';
    const statusText = r.enabled ? 'Aktiv' : 'Deaktiviert';
    return `<tr>
      <td><span class="mini-chip" style="background:${statusBg};color:${statusColor};border-color:${statusColor}">${statusText}</span></td>
      <td class="mono">${escapeHtml(r.protocol)}</td>
      <td class="mono">${escapeHtml(r.source)}</td>
      <td class="mono">${escapeHtml(r.destination)}</td>
      <td class="mono">${escapeHtml(r.port)}</td>
      <td class="mono" style="color:var(--accent)">${escapeHtml(r.target)}</td>
      <td>${escapeHtml(r.description || '—')}</td>
      <td class="mono">${escapeHtml(r.interface || '—')}</td>
    </tr>`;
  }).join('');
}

function natInit() {
  const search = document.getElementById('nat-search');
  if (search) search.addEventListener('input', e => { natFilter = e.target.value; renderNatRules(); });
  refreshNatRules();
}

document.addEventListener('DOMContentLoaded', () => setTimeout(natInit, 300));
setInterval(refreshNatRules, 60_000);