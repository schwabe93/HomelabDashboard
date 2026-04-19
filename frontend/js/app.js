const API = '';
let sortCol = 'rx_5min', sortDir = -1;
let clientFilter = '';
let hostFilter = '';
let expandedClient = null;
let currentTrafficPeriod = 'day';

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
    document.getElementById('sys-cpu').textContent = d.cpu_pct + '%';
    const cpuDot = document.getElementById('sys-cpu-dot');
    cpuDot.className = 'dot dot-pulse' + (d.cpu_pct > 80 ? ' crit' : d.cpu_pct > 60 ? ' warn' : '');
    const ramPct = pct(d.mem_used_mb, d.mem_total_mb);
    document.getElementById('sys-ram').textContent = `${d.mem_used_mb.toLocaleString()} MB`;
    const ramDot = document.getElementById('sys-ram-dot');
    ramDot.className = 'dot' + (ramPct > 80 ? ' crit' : ramPct > 60 ? ' warn' : '');
    document.getElementById('sys-states').textContent = d.active_states.toLocaleString('de-DE');
    document.getElementById('sys-uptime').textContent = formatUptime(d.uptime_str);
    document.getElementById('sys-disk').textContent = d.disk_pct + '%';
    document.getElementById('sys-load').textContent = `${d.load_avg_1} / ${d.load_avg_5}`;
    document.getElementById('last-update').textContent = new Date().toLocaleTimeString('de-DE');
  } catch (e) { console.warn('system', e); }
}

// ── System history ─────────────────────────────────────────────
async function refreshSystemHistory() {
  try {
    const data = await fetchJSON('/api/system/history?hours=6');
    updateSystemChart(data);
  } catch (e) { console.warn('system/history', e); }
}

// ── Interfaces ─────────────────────────────────────────────────
async function refreshInterfaces() {
  try {
    const ifaces = await fetchJSON('/api/interfaces');
    renderIfaceCards(ifaces);
    await refreshIfaceHistories(ifaces);
  } catch (e) { console.warn('interfaces', e); }
}

function renderIfaceCards(ifaces) {
  const grid = document.getElementById('iface-grid');
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

// ── Traffic history ────────────────────────────────────────────
async function refreshTraffic() {
  try {
    // Totals summary
    const totals = await fetchJSON('/api/traffic/totals');
    if (totals.today) {
      document.getElementById('tt-today-rx').textContent = formatBytes(totals.today.rx);
      document.getElementById('tt-today-tx').textContent = '▲ ' + formatBytes(totals.today.tx);
    }
    if (totals.week) {
      document.getElementById('tt-week-rx').textContent = formatBytes(totals.week.rx);
      document.getElementById('tt-week-tx').textContent = '▲ ' + formatBytes(totals.week.tx);
    }
    if (totals.month) {
      document.getElementById('tt-month-rx').textContent = formatBytes(totals.month.rx);
      document.getElementById('tt-month-tx').textContent = '▲ ' + formatBytes(totals.month.tx);
    }
  } catch (e) { console.warn('traffic/totals', e); }

  await refreshTrafficChart(currentTrafficPeriod);
}

async function refreshTrafficChart(period) {
  try {
    const data = await fetchJSON(`/api/traffic/summary?period=${period}`);
    if (!data.rows || data.rows.length === 0) {
      buildTrafficChart(['Keine Daten'], []);
      return;
    }

    // Get unique labels (dates/months) and interfaces
    const labelSet = [...new Set(data.rows.map(r => r.label))];
    const ifaceMap = {};
    data.rows.forEach(r => {
      if (!ifaceMap[r.interface]) ifaceMap[r.interface] = { name: r.iface_name, rx: {}, tx: {} };
      ifaceMap[r.interface].rx[r.label] = r.rx_bytes;
      ifaceMap[r.interface].tx[r.label] = r.tx_bytes;
    });

    const datasets = [];
    Object.entries(ifaceMap).forEach(([iface, info]) => {
      const colors = IFACE_COLORS[iface] || IFACE_COLORS.default;
      datasets.push({
        label: `▼ ${info.name}`,
        data: labelSet.map(l => info.rx[l] || 0),
        backgroundColor: colors.rx,
        borderRadius: 3,
        borderSkipped: false,
      });
      datasets.push({
        label: `▲ ${info.name}`,
        data: labelSet.map(l => info.tx[l] || 0),
        backgroundColor: colors.tx,
        borderRadius: 3,
        borderSkipped: false,
      });
    });

    // Format labels
    const fmtLabels = labelSet.map(l => {
      if (period === 'year') return l; // YYYY-MM
      const d = new Date(l + 'T00:00:00');
      return d.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit' });
    });

    buildTrafficChart(fmtLabels, datasets);
  } catch (e) { console.warn('traffic/summary', e); }
}

function setTrafficPeriod(period, btn) {
  currentTrafficPeriod = period;
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  refreshTrafficChart(period);
}

// ── Clients ────────────────────────────────────────────────────
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
    document.getElementById('clients-count').textContent = clients.length;

    tbody.innerHTML = '';
    clients.forEach(c => {
      const tr = document.createElement('tr');
      tr.style.cursor = 'pointer';
      tr.innerHTML = `
        <td><strong>${c.display || '—'}</strong></td>
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
  if (next && next.classList.contains('sparkline-row')) { next.remove(); expandedClient = null; return; }
  document.querySelector('.sparkline-row')?.remove();
  expandedClient = ip;
  const spark = document.createElement('tr');
  spark.className = 'sparkline-row';
  spark.innerHTML = `<td colspan="7" style="padding:4px 8px 10px"><canvas id="spark-${ip.replace(/\./g,'-')}" height="55"></canvas></td>`;
  tr.after(spark);
  try {
    const hist = await fetchJSON(`/api/clients/history?ip=${ip}&hours=24`);
    updateSparkline(`spark-${ip.replace(/\./g,'-')}`, hist);
  } catch (_) {}
}

function setSortCol(col) {
  if (sortCol === col) sortDir *= -1;
  else { sortCol = col; sortDir = -1; }
  document.querySelectorAll('#clients-table th').forEach(th => th.classList.remove('sorted'));
  document.querySelector(`[data-sort="${col}"]`)?.classList.add('sorted');
  refreshClients();
}

// ── Firewall ───────────────────────────────────────────────────
async function refreshFirewall() {
  try {
    const [states, blocked] = await Promise.all([
      fetchJSON('/api/firewall/states'),
      fetchJSON('/api/firewall/blocked?hours=1'),
    ]);
    document.getElementById('fw-states-count').textContent = states.total.toLocaleString('de-DE');
    const top = document.getElementById('fw-top-tbody');
    top.innerHTML = states.top_sources.slice(0, 10).map(s =>
      `<tr><td class="mono">${s.ip}</td><td>${s.count}</td></tr>`).join('');
    const btbody = document.getElementById('blocked-tbody');
    btbody.innerHTML = blocked.map(b =>
      `<tr><td class="mono">${b.ip}</td><td class="hit-col">${b.hits}</td><td class="mono">${b.protocols}</td><td class="mono">${b.dst_ports}</td></tr>`
    ).join('') || '<tr><td colspan="4" style="text-align:center;color:var(--muted);padding:16px">Keine blockierten IPs</td></tr>';
  } catch (e) { console.warn('firewall', e); }
}

// ── Hosts ──────────────────────────────────────────────────────
async function refreshHosts() {
  try {
    const hosts = await fetchJSON('/api/hosts');
    const tbody = document.getElementById('hosts-tbody');
    let filtered = hosts;
    if (hostFilter) {
      const f = hostFilter.toLowerCase();
      filtered = hosts.filter(h => h.ip.includes(f) || (h.manufacturer||'').toLowerCase().includes(f) || (h.hostname||'').toLowerCase().includes(f));
    }
    document.getElementById('hosts-count').textContent = hosts.length;
    tbody.innerHTML = filtered.map(h =>
      `<tr><td class="mono">${h.ip}</td><td class="mono">${h.mac}</td><td>${h.hostname || h.manufacturer || '<span style="color:var(--muted)">—</span>'}</td><td class="mono">${h.interface}</td></tr>`
    ).join('');
  } catch (e) { console.warn('hosts', e); }
}

// ── Gateways ───────────────────────────────────────────────────
async function refreshGateways() {
  try {
    const gws = await fetchJSON('/api/gateways');
    const body = document.getElementById('gateways-body');
    body.innerHTML = gws.map(gw => {
      const color = gw.online ? 'var(--green)' : 'var(--red)';
      return `<div class="gw-row">
        <div class="gw-left">
          <span style="width:9px;height:9px;border-radius:50%;background:${color};box-shadow:0 0 5px ${color};flex-shrink:0;display:inline-block"></span>
          <div><div class="gw-name">${gw.name}</div><div class="gw-monitor">${gw.monitor}</div></div>
        </div>
        <div class="gw-right">
          <div class="gw-status" style="color:${color}">${gw.status}</div>
          <div class="gw-stats">${gw.delay} &nbsp;·&nbsp; ${gw.loss} loss</div>
        </div></div>`;
    }).join('');
  } catch (e) { console.warn('gateways', e); }
}

// ── WAN IPs ────────────────────────────────────────────────────
async function refreshWan() {
  try {
    const ifaces = await fetchJSON('/api/wan');
    const container = document.getElementById('wan-pills');
    container.innerHTML = ifaces.filter(i => i.addr4).map(i =>
      `<div class="stat-pill"><span class="label">${i.name}</span><span class="value" style="font-family:monospace;font-size:10px">${i.addr4}</span></div>`
    ).join('');
  } catch (e) { console.warn('wan', e); }
}

// ── DNS ────────────────────────────────────────────────────────
async function refreshDns() {
  try {
    const d = await fetchJSON('/api/dns/stats');
    if (d.error) return;
    document.getElementById('dns-queries').textContent  = d.queries.toLocaleString('de-DE');
    document.getElementById('dns-cache-pct').textContent = d.cache_pct + '%';
    document.getElementById('dns-avg-ms').textContent   = d.avg_recursion_ms + ' ms';
    document.getElementById('dns-hits').textContent     = d.cachehits.toLocaleString('de-DE');
    document.getElementById('dns-miss').textContent     = d.cachemiss.toLocaleString('de-DE');
    document.getElementById('dns-cache-bar').style.width = Math.min(d.cache_pct, 100) + '%';
  } catch (e) { console.warn('dns', e); }
}

// ── Interface Errors ───────────────────────────────────────────
async function refreshIfaceErrors() {
  try {
    const data = await fetchJSON('/api/interfaces/errors');
    const tbody = document.getElementById('iface-errors-tbody');
    tbody.innerHTML = data.map(i => {
      const errColor  = i.input_errors  > 0 ? 'var(--red)'    : 'var(--muted)';
      const outColor  = i.output_errors > 0 ? 'var(--red)'    : 'var(--muted)';
      const dropColor = i.queue_drops   > 0 ? 'var(--yellow)' : 'var(--muted)';
      return `<tr>
        <td><strong>${i.name || i.device}</strong><br><span class="mono">${i.device}</span></td>
        <td style="color:${errColor}">${i.input_errors}</td>
        <td style="color:${outColor}">${i.output_errors}</td>
        <td style="color:${dropColor}">${i.queue_drops}</td></tr>`;
    }).join('');
  } catch (e) { console.warn('iface_errors', e); }
}

// ── Main loop ──────────────────────────────────────────────────
async function refreshAll() {
  await Promise.allSettled([
    refreshSystem(),
    refreshInterfaces(),
    refreshClients(),
    refreshFirewall(),
    refreshHosts(),
    refreshGateways(),
    refreshWan(),
    refreshDns(),
    refreshIfaceErrors(),
    refreshTraffic(),
  ]);
}

async function refreshCharts() {
  await Promise.allSettled([refreshSystemHistory()]);
}

// Boot
refreshAll();
refreshCharts();
setInterval(refreshAll, 30_000);
setInterval(refreshCharts, 60_000);

// Search
document.getElementById('client-search').addEventListener('input', e => { clientFilter = e.target.value; refreshClients(); });
document.getElementById('host-search').addEventListener('input',   e => { hostFilter   = e.target.value; refreshHosts();   });
