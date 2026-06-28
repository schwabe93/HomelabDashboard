const API = '';
let sortCol = 'rx_5min', sortDir = -1;
let clientFilter = '';
let hostFilter = '';
let ipdhcpFilter = '';
let ipdhcpSource = '';
let ipdhcpData = null;
let starlinkData = null;
let expandedClient = null;
let currentTrafficPeriod = 'day';
let currentView = 'dashboard';
let ipdhcpLoaded = false;
let starlinkLoaded = false;
let trendsLoaded = false;
let dockerLoaded = false;
let proxmoxLoaded = false;
let uptimeKumaLoaded = false;
let networkLoaded = false;

const DEFAULT_VIEW = 'dashboard';
const VALID_VIEWS = new Set(['dashboard', 'ip-management', 'starlink', 'trends', 'network', 'docker', 'proxmox', 'uptime-kuma']);
const VIEW_TITLES = {
  dashboard: 'Dashboard',
  'ip-management': 'IP Management',
  starlink: 'Starlink',
  trends: 'Trends',
  network: 'Netzwerk',
  docker: 'Docker',
  proxmox: 'Proxmox',
  'uptime-kuma': 'Uptime Kuma',
};

async function fetchJSON(url) {
  const r = await fetch(API + url);
  if (!r.ok) throw new Error(r.status);
  return r.json();
}

function getViewFromHash() {
  const raw = window.location.hash.replace(/^#\/?/, '');
  return VALID_VIEWS.has(raw) ? raw : DEFAULT_VIEW;
}

function navigateTo(view) {
  const target = VALID_VIEWS.has(view) ? view : DEFAULT_VIEW;
  const nextHash = `#/${target}`;
  if (window.location.hash !== nextHash) window.location.hash = nextHash;
  else setView(target);
}

function setView(view) {
  const target = VALID_VIEWS.has(view) ? view : DEFAULT_VIEW;
  currentView = target;

  document.querySelectorAll('.app-tab').forEach(btn => {
    const active = btn.dataset.viewTarget === target;
    btn.classList.toggle('active', active);
    btn.setAttribute('aria-current', active ? 'page' : 'false');
  });

  document.querySelectorAll('[data-view]').forEach(section => {
    const active = section.dataset.view === target;
    section.hidden = !active;
    section.classList.toggle('is-active', active);
  });

  document.body.dataset.currentView = target;
  document.title = `${VIEW_TITLES[target] || 'Dashboard'} · Homelab Dashboard`;
  window.scrollTo({ top: 0, behavior: 'auto' });

  if (target === 'ip-management' && !ipdhcpLoaded) {
    ipdhcpLoaded = true;
    refreshIpdhcp();
  }
  if (target === 'starlink' && !starlinkLoaded) {
    starlinkLoaded = true;
    refreshStarlink();
  }
  if (target === 'trends' && !trendsLoaded) {
    trendsLoaded = true;
    if (window.initTrendsView) initTrendsView();
  }
  if (target === 'network' && !networkLoaded) {
    networkLoaded = true;
    if (window.initNetworkView) initNetworkView();
  }
  if (target === 'docker' && !dockerLoaded) {
    dockerLoaded = true;
    if (window.DockerStatus) DockerStatus.init();
  }
  if (target === 'proxmox' && !proxmoxLoaded) {
    proxmoxLoaded = true;
    if (window.Proxmox) Proxmox.refresh();
  }
  if (target === 'uptime-kuma' && !uptimeKumaLoaded) {
    uptimeKumaLoaded = true;
    if (window.UptimeKuma) UptimeKuma.refresh();
  }
}

function yesNo(value) {
  return value ? 'Ja' : 'Nein';
}

function formatSeconds(value) {
  const seconds = Number(value || 0);
  if (!seconds) return '-';
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const mins = Math.floor((seconds % 3600) / 60);
  if (days) return `${days}d ${hours}h`;
  if (hours) return `${hours}h ${mins}m`;
  return `${mins}m`;
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
  const group = btn?.closest('.tabs');
  group?.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  btn?.classList.add('active');
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

function renderChips(values, kind = '') {
  return `<div class="chip-list">${(values || []).map(v => `<span class="mini-chip ${kind}">${escapeHtml(v)}</span>`).join('')}</div>`;
}

function ipdhcpVisibleHosts() {
  const q = ipdhcpFilter.toLowerCase();
  return (ipdhcpData?.hosts || []).filter(h => {
    const sourceOk = !ipdhcpSource || (h.sources || []).some(s => s.includes(ipdhcpSource));
    const queryOk = !q || JSON.stringify(h).toLowerCase().includes(q);
    return sourceOk && queryOk;
  });
}

function renderIpdhcpSummary(data) {
  const counts = data.counts || {};
  const opn = counts.opnsense || {};
  const stats = [
    [counts.consolidated_ips || 0, 'IPs'],
    [counts.total_items || 0, 'Eintraege'],
    [opn.leases || 0, 'DHCP'],
    [counts.unraid_items || 0, 'Unraid'],
  ];
  document.getElementById('ipdhcp-summary').innerHTML = stats.map(([value, label]) =>
    `<div class="stat-box"><div class="big-num">${escapeHtml(value)}</div><div class="big-label">${escapeHtml(label)}</div></div>`
  ).join('');
  document.getElementById('ipdhcp-count').textContent = `${counts.consolidated_ips || 0} IPs`;
}

function renderIpdhcpHosts() {
  const tbody = document.getElementById('ipdhcp-tbody');
  const rows = ipdhcpVisibleHosts();
  tbody.innerHTML = rows.map(h => `
    <tr>
      <td class="mono">${escapeHtml(h.ip)}</td>
      <td>${renderChips(h.names)}</td>
      <td>${renderChips(h.macs)}</td>
      <td>${renderChips(h.sources, 'source')}</td>
      <td>${renderChips(h.interfaces)}</td>
      <td>${renderChips(h.statuses)}</td>
      <td>${renderChips(h.details)}</td>
    </tr>
  `).join('') || '<tr><td colspan="7" class="loading">Keine passenden Eintraege</td></tr>';
}

function renderIpdhcpHistory() {
  const tbody = document.getElementById('ipdhcp-history');
  tbody.innerHTML = (ipdhcpData?.history || []).slice(0, 60).map(h => `
    <tr>
      <td>${escapeHtml(h.first_seen)}</td>
      <td>${escapeHtml(h.last_seen)}</td>
      <td class="mono">${escapeHtml(h.mac)}</td>
      <td>${renderChips(h.names)}</td>
      <td>${renderChips(h.ips)}</td>
    </tr>
  `).join('') || '<tr><td colspan="5" class="loading">Keine History</td></tr>';
}

function renderIpdhcpLeasePicker() {
  const leases = (ipdhcpData?.items || [])
    .filter(item => item.type === 'dhcp' && item.mac && item.ip)
    .sort((a, b) => a.ip.localeCompare(b.ip, undefined, { numeric: true }));
  const picker = document.getElementById('ipdhcp-lease-pick');
  picker.innerHTML = '<option value="">Manuell ausfuellen</option>' + leases.map((item, index) => {
    const label = `${item.ip} - ${item.name || '(kein Name)'} - ${item.mac}`;
    return `<option value="${index}">${escapeHtml(label)}</option>`;
  }).join('');
  picker._leases = leases;
}

function renderIpdhcpVmMacs() {
  const rows = (ipdhcpData?.unraid_vm_macs || []).filter(vm => {
    return !(ipdhcpData?.items || []).some(item => item.type === 'vm' && item.name === vm.name);
  });
  document.getElementById('ipdhcp-vm-macs').innerHTML = rows.length
    ? rows.map(vm => `<span class="mini-chip">${escapeHtml(vm.name)}: ${escapeHtml((vm.macs || []).join(', '))}</span>`).join('')
    : '<span class="mini-chip">Keine</span>';
}

async function refreshIpdhcp() {
  const errors = document.getElementById('ipdhcp-errors');
  const button = document.getElementById('ipdhcp-refresh');
  button.disabled = true;
  try {
    ipdhcpData = await fetchJSON('/api/ipdhcp/hosts');
    renderIpdhcpSummary(ipdhcpData);
    renderIpdhcpHosts();
    renderIpdhcpHistory();
    renderIpdhcpLeasePicker();
    renderIpdhcpVmMacs();
    errors.style.display = ipdhcpData.errors?.length ? 'flex' : 'none';
    errors.textContent = (ipdhcpData.errors || []).join(' | ');
  } catch (e) {
    errors.style.display = 'flex';
    errors.textContent = `IP/DHCP konnte nicht geladen werden: ${e.message}`;
  } finally {
    button.disabled = false;
  }
}

function renderStarlinkSummary(data) {
  const status = data.grpc?.status || {};
  const latency = status.pop_ping_latency_ms;
  const stats = [
    [yesNo(data.reachable), 'Ping'],
    [yesNo(data.grpc_open), 'gRPC'],
    [latency == null ? '-' : `${latency} ms`, 'Latenz'],
    [formatSeconds(status.uptime_s), 'Uptime'],
  ];
  document.getElementById('starlink-summary').innerHTML = stats.map(([value, label]) =>
    `<div class="stat-box"><div class="big-num">${escapeHtml(value)}</div><div class="big-label">${escapeHtml(label)}</div></div>`
  ).join('');
  const online = data.reachable || data.grpc_open;
  document.getElementById('starlink-state').textContent = online ? 'online' : 'offline';
  document.getElementById('starlink-state').style.color = online ? 'var(--green)' : 'var(--red)';
  document.getElementById('starlink-host').textContent = `${data.host}${data.ip ? ` (${data.ip})` : ''}`;
}

function metricRow(label, value) {
  return `<tr><td>${escapeHtml(label)}</td><td class="mono">${escapeHtml(value ?? '-')}</td></tr>`;
}

function renderStarlink(data) {
  const grpc = data.grpc || {};
  const status = grpc.status || {};
  renderStarlinkSummary(data);

  // History summary
  const hist = data.history?.history || {};
  const summary = hist.summary || {};
  const histBoxes = [
    [summary.avg_latency_ms != null ? `${summary.avg_latency_ms}` : '-', 'Ø Latenz'],
    [summary.max_latency_ms != null ? `${summary.max_latency_ms}` : '-', 'Max Latenz'],
    [summary.avg_drop_rate != null ? `${(summary.avg_drop_rate * 100).toFixed(1)}%` : '-', 'Ø Drop'],
    [summary.unavailable_pct != null ? `${summary.unavailable_pct}%` : '-', 'Unavailable'],
    [summary.p95_latency_ms != null ? `${summary.p95_latency_ms}` : '-', 'P95 Latenz'],
    [summary.avg_downlink_bps != null ? formatBits(summary.avg_downlink_bps) : '-', 'Ø Download'],
  ];
  document.getElementById('starlink-history-summary').innerHTML = histBoxes.map(([value, label]) =>
    `<div class="stat-box"><div class="big-num">${escapeHtml(value)}</div><div class="big-label">${escapeHtml(label)}</div></div>`
  ).join('');

  // Render charts
  if (hist.ping_latency_ms || hist.ping_drop_rate) {
    updateStarlinkLatencyChart(hist.ping_latency_ms || [], hist.ping_drop_rate || []);
  }
  if (hist.downlink_bps || hist.uplink_bps) {
    updateStarlinkThroughputChart(hist.downlink_bps || [], hist.uplink_bps || []);
  }

  // Alerts
  const alerts = status.alerts || {};
  const activeAlerts = Object.entries(alerts).filter(([k, v]) => v === true);
  const alertsLabel = document.getElementById('starlink-alerts-label');
  const alertsBox = document.getElementById('starlink-alerts');
  if (activeAlerts.length) {
    alertsLabel.style.display = '';
    alertsBox.innerHTML = activeAlerts.map(([key]) =>
      `<span class="mini-chip" style="border-color:var(--red);color:var(--red)">⚠️ ${escapeHtml(key.replace(/_/g, ' '))}</span>`
    ).join('');
  } else {
    alertsLabel.style.display = 'none';
    alertsBox.innerHTML = '';
  }

  // Obstruction stats
  const obs = status.obstruction_stats || {};
  const hasObs = Object.values(obs).some(v => v != null);
  const obsLabel = document.getElementById('starlink-obstruction-label');
  const obsWrap = document.getElementById('starlink-obstruction-wrap');
  if (hasObs) {
    obsLabel.style.display = '';
    obsWrap.style.display = '';
    document.getElementById('starlink-obstruction').innerHTML = [
      metricRow('Fraction Obstructed', obs.fraction_obstructed != null ? `${(obs.fraction_obstructed * 100).toFixed(2)}%` : '-'),
      metricRow('Currently Obstructed', obs.currently_obstructed ? 'Ja' : 'Nein'),
      metricRow('Valid', obs.valid_s != null ? `${obs.valid_s}s` : '-'),
      metricRow('Time Obstructed', obs.time_obstructed != null ? `${obs.time_obstructed}s` : '-'),
      metricRow('Time Obstructed %', obs.time_obstructed_pct != null ? `${obs.time_obstructed_pct}%` : '-'),
      metricRow('Patches Obstructed', obs.patches_obstructed),
      metricRow('Avg Prolonged Obstruction', obs.avg_prolonged_obstruction_interval_s != null ? `${obs.avg_prolonged_obstruction_interval_s}s` : '-'),
    ].join('');
  } else {
    obsLabel.style.display = 'none';
    obsWrap.style.display = 'none';
  }

  document.getElementById('starlink-connection').innerHTML = [
    metricRow('Host', data.host),
    metricRow('IP', data.ip),
    metricRow('HTTP', data.http?.reachable ? `HTTP ${data.http.status_code}` : data.http?.error || 'nicht erreichbar'),
    metricRow('gRPC Port', `${data.grpc_port} ${data.grpc_open ? 'offen' : 'geschlossen'}`),
    metricRow('grpcurl', grpc.available ? 'installiert' : 'nicht installiert'),
    metricRow('Aktualisiert', data.generated_at),
    metricRow('Laufzeit', `${data.duration_ms} ms`),
    metricRow('Hardware', status.hardware_version),
    metricRow('Country', status.country_code),
  ].join('');

  document.getElementById('starlink-metrics').innerHTML = [
    metricRow('Dish ID', status.id),
    metricRow('Status', status.state),
    metricRow('Software', status.software_version),
    metricRow('Bootcount', status.bootcount),
    metricRow('Uptime', formatSeconds(status.uptime_s)),
    metricRow('Ping Latenz', status.pop_ping_latency_ms == null ? '-' : `${status.pop_ping_latency_ms} ms`),
    metricRow('Ping Drop Rate', status.pop_ping_drop_rate != null ? `${(status.pop_ping_drop_rate * 100).toFixed(2)}%` : '-'),
    metricRow('Initial Ping Drop', status.initial_ping_drop_rate != null ? `${(status.initial_ping_drop_rate * 100).toFixed(2)}%` : '-'),
    metricRow('Downlink', status.downlink_throughput_bps == null ? '-' : formatBits(status.downlink_throughput_bps)),
    metricRow('Uplink', status.uplink_throughput_bps == null ? '-' : formatBits(status.uplink_throughput_bps)),
    metricRow('Sec to Nonempty Slot', status.seconds_to_first_nonempty_slot),
    metricRow('Mobile Country Code', status.mobile_country_code),
    metricRow('Mobile Network Code', status.mobile_network_code),
  ].join('');

  const errors = [];
  if (grpc.error) errors.push(grpc.error);
  if (!grpc.available) errors.push('Fuer echte Dish-Statuswerte grpcurl auf dem Server installieren.');
  if (data.history?.error) errors.push(data.history.error);
  if (!data.history?.available && grpc.available) errors.push('History-Daten konnten nicht abgerufen werden.');
  const errorBox = document.getElementById('starlink-errors');
  errorBox.style.display = errors.length ? 'flex' : 'none';
  errorBox.textContent = errors.join(' | ');
  document.getElementById('starlink-raw').textContent = JSON.stringify(data, null, 2);
}

async function refreshStarlink() {
  const button = document.getElementById('starlink-refresh');
  button.disabled = true;
  try {
    starlinkData = await fetchJSON('/api/starlink/status');
    renderStarlink(starlinkData);
  } catch (e) {
    document.getElementById('starlink-errors').style.display = 'flex';
    document.getElementById('starlink-errors').textContent = `Starlink konnte nicht geladen werden: ${e.message}`;
  } finally {
    button.disabled = false;
  }
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
window.addEventListener('hashchange', () => setView(getViewFromHash()));
document.querySelectorAll('.app-tab').forEach(btn => btn.addEventListener('click', () => navigateTo(btn.dataset.viewTarget)));
document.querySelectorAll('[data-traffic-period]').forEach(btn => btn.addEventListener('click', () => setTrafficPeriod(btn.dataset.trafficPeriod, btn)));
setView(getViewFromHash());
refreshAll();
refreshCharts();
setInterval(refreshAll, 30_000);
setInterval(refreshCharts, 60_000);
setInterval(() => { if (ipdhcpLoaded) refreshIpdhcp(); }, 300_000);
setInterval(() => { if (starlinkLoaded) refreshStarlink(); }, 60_000);

// Search
document.getElementById('client-search').addEventListener('input', e => { clientFilter = e.target.value; refreshClients(); });
document.getElementById('host-search').addEventListener('input',   e => { hostFilter   = e.target.value; refreshHosts();   });
document.getElementById('ipdhcp-search').addEventListener('input', e => { ipdhcpFilter = e.target.value; renderIpdhcpHosts(); });
document.getElementById('ipdhcp-source').addEventListener('change', e => { ipdhcpSource = e.target.value; renderIpdhcpHosts(); });
document.getElementById('ipdhcp-refresh').addEventListener('click', refreshIpdhcp);
document.getElementById('starlink-refresh').addEventListener('click', refreshStarlink);
document.getElementById('ipdhcp-lease-pick').addEventListener('change', e => {
  const item = e.target._leases?.[Number(e.target.value)];
  if (!item) return;
  document.getElementById('ipdhcp-ip').value = item.ip || '';
  document.getElementById('ipdhcp-mac').value = item.mac || '';
  document.getElementById('ipdhcp-hostname').value = item.name && item.name !== '*' ? item.name : '';
  document.getElementById('ipdhcp-description').value = `Static lease for ${item.name || item.mac}`;
});
document.getElementById('ipdhcp-lease-form').addEventListener('submit', async e => {
  e.preventDefault();
  const result = document.getElementById('ipdhcp-result');
  result.textContent = 'Speichere...';
  try {
    const r = await fetch(API + '/api/ipdhcp/static-lease', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        hostname: document.getElementById('ipdhcp-hostname').value,
        ip: document.getElementById('ipdhcp-ip').value,
        mac: document.getElementById('ipdhcp-mac').value,
        description: document.getElementById('ipdhcp-description').value,
        apply: document.getElementById('ipdhcp-apply').checked,
      }),
    });
    const body = await r.json();
    if (!r.ok || !body.ok) throw new Error(body.detail || body.error || 'Speichern fehlgeschlagen');
    result.textContent = 'Static Lease gespeichert.';
    await refreshIpdhcp();
  } catch (err) {
    result.textContent = err.message;
  }
});
