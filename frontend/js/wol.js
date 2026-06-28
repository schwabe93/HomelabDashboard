// ── Wake-on-LAN (WoL) ──────────────────────────────────────────────
// Adds WoL buttons to the ARP/hosts table and a recent-attempts panel.
// Depends on: fetchJSON, escapeHtml (utils.js / app.js)

let wolRecent = [];

// Inject a WoL action column header into the hosts table (called on init)
function wolInitHostsColumn() {
  const table = document.querySelector('[data-view="dashboard"] table thead');
  if (!table) return;
  const ths = table.querySelectorAll('th');
  if (ths.length && !ths[ths.length - 1].dataset.wol) {
    const th = document.createElement('th');
    th.dataset.wol = '1';
    th.textContent = 'WoL';
    th.style.cursor = 'default';
    table.appendChild(th);
  }
}

// Send a WoL magic packet
async function wolSend(mac, broadcastIp = '255.255.255.255', hostname = '', ip = '') {
  if (!mac) return;
  const btn = document.querySelector(`[data-wol-mac="${CSS.escape(mac)}"]`);
  if (btn) { btn.disabled = true; btn.textContent = '⏳'; }
  try {
    const r = await fetch(API + '/api/wol/send', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mac, broadcast_ip: broadcastIp, hostname, ip }),
    });
    const body = await r.json();
    if (btn) {
      btn.textContent = body.ok ? '✓' : '✗';
      btn.style.color = body.ok ? 'var(--green)' : 'var(--red)';
      setTimeout(() => { btn.disabled = false; btn.textContent = '⚡ Wecken'; btn.style.color = ''; }, 2500);
    }
    wolRefreshRecent();
  } catch (e) {
    if (btn) { btn.textContent = '✗'; btn.style.color = 'var(--red)'; setTimeout(() => { btn.disabled = false; btn.textContent = '⚡ Wecken'; btn.style.color = ''; }, 2500); }
    console.warn('wol send', e);
  }
}

// Patch refreshHosts to add WoL buttons. We wrap the existing function.
const _wolOriginalRefreshHosts = window.refreshHosts;
window.refreshHosts = async function wolRefreshHostsPatched() {
  await _wolOriginalRefreshHosts.apply(this, arguments);
  // Append WoL button column to each row
  const tbody = document.getElementById('hosts-tbody');
  if (!tbody) return;
  // Ensure header column exists
  const thead = tbody.closest('table')?.querySelector('thead tr');
  if (thead && !thead.querySelector('[data-wol]')) {
    const th = document.createElement('th');
    th.dataset.wol = '1';
    th.textContent = 'WoL';
    th.style.cursor = 'default';
    thead.appendChild(th);
  }
  tbody.querySelectorAll('tr').forEach(tr => {
    if (tr.querySelector('[data-wol-cell]')) return;
    // Extract MAC from the 2nd cell (mono class)
    const cells = tr.querySelectorAll('td');
    if (cells.length < 2) return;
    const macText = cells[1].textContent.trim();
    const ipText = cells[0].textContent.trim();
    const hostText = cells[2] ? cells[2].textContent.trim() : '';
    if (!macText || !/^[0-9a-f:]{12,17}$/i.test(macText)) return;
    const td = document.createElement('td');
    td.dataset.wolCell = '1';
    const btn = document.createElement('button');
    btn.className = 'tab-btn';
    btn.dataset.wolMac = macText;
    btn.textContent = '⚡ Wecken';
    btn.style.padding = '2px 8px';
    btn.style.fontSize = '10px';
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      wolSend(macText, '192.168.188.255', hostText, ipText);
    });
    td.appendChild(btn);
    tr.appendChild(td);
  });
};

// Recent wake attempts panel
async function wolRefreshRecent() {
  try {
    wolRecent = await fetchJSON('/api/wol/recent?limit=20');
    wolRenderRecent();
  } catch (e) { console.warn('wol/recent', e); }
}

function wolRenderRecent() {
  const body = document.getElementById('wol-recent-body');
  if (!body) return;
  if (!wolRecent.length) {
    body.innerHTML = '<div class="loading">Noch keine WoL-Versuche.</div>';
    return;
  }
  body.innerHTML = wolRecent.map(r => {
    const color = r.status === 'ok' ? 'var(--green)' : 'var(--red)';
    const icon = r.status === 'ok' ? '✓' : '✗';
    return `<div class="wol-event">
      <span class="wol-status" style="color:${color}">${icon}</span>
      <span class="wol-mac mono">${escapeHtml(r.mac)}</span>
      ${r.hostname ? `<span class="wol-name">${escapeHtml(r.hostname)}</span>` : ''}
      <span class="wol-time">${escapeHtml(r.time)}</span>
    </div>`;
  }).join('');
}

// Manual MAC input form submit
async function wolManualSend(e) {
  e.preventDefault();
  const macInput = document.getElementById('wol-manual-mac');
  const bcastInput = document.getElementById('wol-manual-broadcast');
  if (!macInput) return;
  const mac = macInput.value.trim().toLowerCase();
  const broadcast = bcastInput ? bcastInput.value.trim() : '192.168.188.255';
  if (!mac) return;
  await wolSend(mac, broadcast, 'Manuell', '');
  macInput.value = '';
}

// Init when the WoL panel is present
function wolInit() {
  wolInitHostsColumn();
  const form = document.getElementById('wol-manual-form');
  if (form) form.addEventListener('submit', wolManualSend);
  wolRefreshRecent();
}

// Run init on load (panel may not exist until merge; guard with checks)
document.addEventListener('DOMContentLoaded', () => setTimeout(wolInit, 300));
setInterval(wolRefreshRecent, 60_000);