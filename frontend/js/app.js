const API = '';
let sortCol = 'rx_5min', sortDir = -1;
let clientFilter = '';
let hostFilter = '';
let expandedClient = null;

async function fetchJSON(url) {
  const r = await fetch(API + url);
  if (!r.ok) throw new Error(r.status);
  return r.json();
}

// ── System header ──────────────────────────────────────────────
async function refreshSystem() {
  try {
    const d = await fetchJSON('/api/system');
    document.getElementById('sys-hostname').textContent = d.hostname;
    document.getElementById('sys-version').textContent = d.version;
    document.getElementById('sys-cpu').textContent = d.cpu_pct + '%';
    document.getElementById('sys-cpu-dot').className = 'dot' + (d.cpu_pct > 80 ? ' crit' : d.cpu_pct > 60 ? ' warn' : '');
    document.getElementById('sys-ram').textContent = `${d.mem_used_mb} / ${d.mem_total_mb} MB`;
    document.getElementById('sys-ram-dot').className = 'dot' + (pct(d.mem_used_mb, d.mem_total_mb) > 80 ? ' crit' : pct(d.mem_used_mb, d.mem_total_mb) > 60 ? ' warn' : '');
    document.getElementById('sys-states').textContent = d.active_states.toLocaleString();
    document.getElementById('sys-uptime').textContent = formatUptime(d.uptime_str);
    document.getElementById('sys-disk').textContent = d.disk_pct + '%';
    document.getElementById('sys-load').textContent = `${d.load_avg_1} / ${d.load_avg_5} / ${d.load_avg_15}`;
    document.getElementById('last-update').textContent = 'Updated: ' + new Date().toLocaleTimeString('de-DE');
  } catch (e) { console.warn('system', e); }
}

// ── System history chart ────────────────────────────────────────
async function refreshSystemHistory() {
  try {
    const data = await fetchJSON('/api/system/history?hours=6');
    updateSystemChart(data);
  } catch (e) { console.warn('system/history', e); }
}

// ── Interface traffic ───────────────────────────────────────────
let ifaceData = [];

async function refreshInterfaces() {
  try {
    const ifaces = await fetchJSON('/api/interfaces');
    ifaceData = ifaces;
    renderIfaceCards(ifaces);
    await refreshIfaceHistories(ifaces);
  } catch (e) { console.warn('interfaces', e); }
}

function renderIfaceCards(ifaces) {
  const grid = document.getElementById('iface-grid');
  const existing = new Set(grid.querySelectorAll('.iface-card').length > 0
    ? [...grid.querySelectorAll('.iface-card')].map(el => el.dataset.iface)
    : []);

  ifaces.forEach(iface => {
    let card = grid.querySelector(`[data-iface="${iface.interface}"]`);
    if (!card) {
      card = document.createElement('div');
      card.className = 'iface-card';
      card.dataset.iface = iface.interface;
      card.innerHTML = `
        <div class="iface-name">${iface.name}</div>
        <div class="iface-rates">
          <span class="rx">▼ <span id="rx-${iface.interface}">…</span></span>
          <span class="tx">▲ <span id="tx-${iface.interface}">…</span></span>
        </div>
        <div class="chart-wrap"><canvas id="chart-iface-${iface.interface}"></canvas></div>`;
      grid.appendChild(card);
    }
    document.getElementById(`rx-${iface.interface}`).textContent = formatBits(iface.rx_rate_bps);
    document.getElementById(`tx-${iface.interface}`).textContent = formatBits(iface.tx_rate_bps);
  });
}

async function refreshIfaceHistories(ifaces) {
  await Promise.allSettled(ifaces.map(async iface => {
    try {
      const hist = await fetchJSON(`/api/interfaces/history?iface=${iface.interface}&hours=1`);
      updateIfaceChart(`chart-iface-${iface.interface}`, hist);
    } catch (_) {}
  }));
}

// ── Per-client bandwidth ────────────────────────────────────────
async function refreshClients() {
  try {
    const data = await fetchJSON('/api/clients');
    const tbody = document.getElementById('clients-tbody');
    const banner = document.getElementById('netflow-banner');

    if (!data.netflow_enabled) {
      banner.style.display = 'flex';
      tbody.innerHTML = '';
      return;
    }
    banner.style.display = 'none';

    let clients = [...data.clients];
    clients.sort((a, b) => (a[sortCol] < b[sortCol] ? sortDir : -sortDir));

    if (clientFilter) {
      const f = clientFilter.toLowerCase();
      clients = clients.filter(c => c.ip.includes(f) || c.display.toLowerCase().includes(f));
    }

    tbody.innerHTML = '';
    clients.forEach((c, i) => {
      const tr = document.createElement('tr');
      tr.style.cursor = 'pointer';
      tr.innerHTML = `
        <td>${c.display || '—'}</td>
        <td class="mono">${c.ip}</td>
        <td class="mono">${c.mac || '—'}</td>
        <td class="rx-col">${formatBytes(c.rx_5min)}</td>
        <td class="tx-col">${formatBytes(c.tx_5min)}</td>
        <td class="rx-col">${formatBytes(c.rx_today)}</td>
        <td class="tx-col">${formatBytes(c.tx_today)}</td>`;
      tr.addEventListener('click', () => toggleSparkline(c.ip, tr));
      tbody.appendChild(tr);
    });
  } catch (e) { console.warn('clients', e); }
}

async function toggleSparkline(ip, tr) {
  const next = tr.nextElementSibling;
  if (next && next.classList.contains('sparkline-row')) {
    next.remove();
    expandedClient = null;
    return;
  }
  if (expandedClient) {
    const old = document.querySelector('.sparkline-row');
    if (old) old.remove();
  }
  expandedClient = ip;
  const spark = document.createElement('tr');
  spark.className = 'sparkline-row';
  spark.innerHTML = `<td colspan="7"><canvas id="spark-${ip.replace(/\./g, '-')}" height="60"></canvas></td>`;
  tr.after(spark);
  try {
    const hist = await fetchJSON(`/api/clients/history?ip=${ip}&hours=24`);
    updateSparkline(`spark-${ip.replace(/\./g, '-')}`, hist);
  } catch (_) {}
}

function setSortCol(col) {
  if (sortCol === col) sortDir *= -1;
  else { sortCol = col; sortDir = -1; }
  document.querySelectorAll('#clients-table th').forEach(th => th.classList.remove('sorted'));
  document.querySelector(`[data-sort="${col}"]`)?.classList.add('sorted');
  refreshClients();
}

// ── Firewall ────────────────────────────────────────────────────
async function refreshFirewall() {
  try {
    const [states, blocked] = await Promise.all([
      fetchJSON('/api/firewall/states'),
      fetchJSON('/api/firewall/blocked?hours=1'),
    ]);

    document.getElementById('fw-states-count').textContent = states.total.toLocaleString();

    // Top sources table
    const tbody = document.getElementById('fw-top-tbody');
    tbody.innerHTML = '';
    states.top_sources.slice(0, 10).forEach(s => {
      const tr = document.createElement('tr');
      tr.innerHTML = `<td class="mono">${s.ip}</td><td>${s.count}</td>`;
      tbody.appendChild(tr);
    });

    // Blocked IPs
    const btbody = document.getElementById('blocked-tbody');
    btbody.innerHTML = '';
    blocked.forEach(b => {
      const tr = document.createElement('tr');
      tr.innerHTML = `<td class="mono">${b.ip}</td><td class="hit-col">${b.hits}</td><td class="mono">${b.protocols}</td><td class="mono">${b.dst_ports}</td>`;
      btbody.appendChild(tr);
    });
  } catch (e) { console.warn('firewall', e); }
}

// ── ARP / Hosts ─────────────────────────────────────────────────
async function refreshHosts() {
  try {
    const hosts = await fetchJSON('/api/hosts');
    const tbody = document.getElementById('hosts-tbody');
    let filtered = hosts;
    if (hostFilter) {
      const f = hostFilter.toLowerCase();
      filtered = hosts.filter(h => h.ip.includes(f) || (h.manufacturer || '').toLowerCase().includes(f) || (h.hostname || '').toLowerCase().includes(f));
    }
    tbody.innerHTML = '';
    filtered.forEach(h => {
      const tr = document.createElement('tr');
      const display = h.hostname || h.manufacturer || '—';
      tr.innerHTML = `<td class="mono">${h.ip}</td><td class="mono">${h.mac}</td><td>${display}</td><td class="mono">${h.interface}</td>`;
      tbody.appendChild(tr);
    });
    document.getElementById('hosts-count').textContent = hosts.length;
  } catch (e) { console.warn('hosts', e); }
}

// ── Main loop ───────────────────────────────────────────────────
async function refreshAll() {
  await Promise.allSettled([
    refreshSystem(),
    refreshInterfaces(),
    refreshClients(),
    refreshFirewall(),
    refreshHosts(),
  ]);
}

async function refreshCharts() {
  await Promise.allSettled([
    refreshSystemHistory(),
  ]);
}

// Initial load
refreshAll();
refreshCharts();
setInterval(refreshAll, 30_000);
setInterval(refreshCharts, 60_000);

// Search boxes
document.getElementById('client-search').addEventListener('input', e => {
  clientFilter = e.target.value;
  refreshClients();
});
document.getElementById('host-search').addEventListener('input', e => {
  hostFilter = e.target.value;
  refreshHosts();
});
