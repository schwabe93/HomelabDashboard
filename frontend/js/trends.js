/* ──────────────────────────────────────────────────────────────
 * Trends – Langzeit-Trend-Charts (7d / 30d / 1yr)
 * Feature 1: System Health + Traffic Trends
 * Feature 2: Monthly Traffic Report
 *
 * Wird über app.js geladen und beim Wechsel in den "trends"-View aktiviert.
 * ────────────────────────────────────────────────────────────── */

let trendsLoaded = false;
let currentTrendsPeriod = '7d';
let reportChartInstance = null;

async function fetchJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(r.status);
  return r.json();
}

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function formatBytes(bytes, decimals = 1) {
  if (!bytes || bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB', 'PB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(decimals)) + ' ' + sizes[i];
}

// ── Perioden-Selektor ─────────────────────────────────────────
function setTrendsPeriod(period, btn) {
  currentTrendsPeriod = period;
  const group = btn?.closest('.tabs');
  group?.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  btn?.classList.add('active');
  refreshTrends();
}

// ── Haupt-Render ──────────────────────────────────────────────
async function refreshTrends() {
  await Promise.allSettled([
    refreshTrendsSystem(),
    refreshTrendsTraffic(),
  ]);
  updateTrendsSummary();
}

// ── System Health Trend ───────────────────────────────────────
async function refreshTrendsSystem() {
  try {
    const data = await fetchJSON(`/api/trends/system?period=${currentTrendsPeriod}`);
    renderTrendsSystemChart(data);
    renderTrendsSystemSummary(data);
  } catch (e) { console.warn('trends/system', e); }
}

// ── Traffic Trend ─────────────────────────────────────────────
async function refreshTrendsTraffic() {
  try {
    const data = await fetchJSON(`/api/trends/traffic?period=${currentTrendsPeriod}`);
    renderTrendsTrafficChart(data);
    renderTrendsTrafficSummary(data);
  } catch (e) { console.warn('trends/traffic', e); }
}

// ── Charts ────────────────────────────────────────────────────
const trendsSystemChart = { instance: null };
const trendsTrafficChart = { instance: null };

const TRENDS_COLORS = {
  cpu: '#f85149',
  cpu_fill: 'rgba(248,81,73,.1)',
  ram: '#bc8cff',
  ram_fill: 'rgba(188,140,255,.1)',
  load: '#f59e0b',
  rx: '#3fb950',
  tx: '#58a6ff',
};

const IFACE_COLORS = {
  pppoe0:  { rx: '#f0883e', tx: 'rgba(240,136,62,.4)' },
  vtnet2:  { rx: '#bc8cff', tx: 'rgba(188,140,255,.4)' },
  vtnet0:  { rx: '#58a6ff', tx: 'rgba(88,166,255,.4)' },
  vtnet1:  { rx: '#3fb950', tx: 'rgba(63,185,80,.4)' },
  default: { rx: '#8b949e', tx: 'rgba(139,148,158,.4)' },
};

function renderTrendsSystemChart(data) {
  const ctx = document.getElementById('chart-trends-system');
  if (!ctx) return;
  if (trendsSystemChart.instance) trendsSystemChart.instance.destroy();

  const labels = (data.points || []).map(p => _formatBucketLabel(p.ts, currentTrendsPeriod));
  trendsSystemChart.instance = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [
        { label: 'CPU Ø %', data: (data.points||[]).map(p => p.cpu_avg), borderColor: TRENDS_COLORS.cpu, backgroundColor: TRENDS_COLORS.cpu_fill, borderWidth: 1.5, pointRadius: 0, fill: true, tension: 0.3, yAxisID: 'y' },
        { label: 'CPU Max %', data: (data.points||[]).map(p => p.cpu_max), borderColor: TRENDS_COLORS.cpu, backgroundColor: 'transparent', borderWidth: 1, pointRadius: 0, fill: false, tension: 0.3, borderDash: [4,3], yAxisID: 'y' },
        { label: 'RAM Ø %', data: (data.points||[]).map(p => p.mem_avg), borderColor: TRENDS_COLORS.ram, backgroundColor: TRENDS_COLORS.ram_fill, borderWidth: 1.5, pointRadius: 0, fill: true, tension: 0.3, yAxisID: 'y' },
        { label: 'Load Ø', data: (data.points||[]).map(p => p.load_avg), borderColor: TRENDS_COLORS.load, backgroundColor: 'transparent', borderWidth: 1.5, pointRadius: 0, fill: false, tension: 0.3, yAxisID: 'y1' },
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false, animation: { duration: 300 },
      plugins: { legend: { display: true, labels: { color: '#94a3b8', font: { size: 10 }, boxWidth: 12 } } },
      scales: {
        x: { ticks: { color: '#94a3b8', font: { size: 9 }, maxTicksLimit: 12 }, grid: { color: '#21262d' } },
        y: { min: 0, max: 100, ticks: { color: '#94a3b8', font: { size: 10 }, callback: v => v + '%' }, grid: { color: '#21262d' }, beginAtZero: true },
        y1: { position: 'right', ticks: { color: '#f59e0b', font: { size: 10 } }, grid: { display: false }, beginAtZero: true },
      },
    },
  });
}

function renderTrendsSystemSummary(data) {
  const el = document.getElementById('trends-system-summary');
  if (!el) return;
  const s = data.summary || {};
  if (!s.cpu_min && !s.cpu_max) { el.innerHTML = '<tr><td colspan="5" class="loading">Keine Daten</td></tr>'; return; }
  el.innerHTML = `
    <tr><td>CPU %</td><td>${s.cpu_min ?? '-'}</td><td><strong>${s.cpu_avg ?? '-'}</strong></td><td>${s.cpu_max ?? '-'}</td></tr>
    <tr><td>RAM %</td><td>${s.mem_min ?? '-'}</td><td><strong>${s.mem_avg ?? '-'}</strong></td><td>${s.mem_max ?? '-'}</td></tr>
    <tr><td>Load</td><td>${s.load_min ?? '-'}</td><td><strong>${s.load_avg ?? '-'}</strong></td><td>${s.load_max ?? '-'}</td></tr>
  `;
}

function renderTrendsTrafficChart(data) {
  const ctx = document.getElementById('chart-trends-traffic');
  if (!ctx) return;
  if (trendsTrafficChart.instance) trendsTrafficChart.instance.destroy();

  const labels = (data.buckets || []).map(b => _formatBucketLabel(b, currentTrendsPeriod));
  const datasets = [];
  (data.interfaces || []).forEach(iface => {
    const colors = IFACE_COLORS[iface.interface] || IFACE_COLORS.default;
    datasets.push({
      label: `▼ ${iface.iface_name}`,
      data: (data.buckets || []).map(b => iface.rx[b]?.total || iface.rx[b]?.avg || 0),
      borderColor: colors.rx, backgroundColor: colors.rx + '55', borderWidth: 1.5, pointRadius: 0, fill: false, tension: 0.3,
    });
    datasets.push({
      label: `▲ ${iface.iface_name}`,
      data: (data.buckets || []).map(b => iface.tx[b]?.total || iface.tx[b]?.avg || 0),
      borderColor: colors.tx, backgroundColor: 'transparent', borderWidth: 1.5, pointRadius: 0, fill: false, tension: 0.3, borderDash: [4,3],
    });
  });

  trendsTrafficChart.instance = new Chart(ctx, {
    type: 'line',
    data: { labels, datasets },
    options: {
      responsive: true, maintainAspectRatio: false, animation: { duration: 300 },
      plugins: {
        legend: { display: true, labels: { color: '#94a3b8', font: { size: 10 }, boxWidth: 12 } },
        tooltip: { callbacks: { label: ctx => ` ${ctx.dataset.label}: ${formatBytes(ctx.parsed.y)}` } },
      },
      scales: {
        x: { ticks: { color: '#94a3b8', font: { size: 9 }, maxTicksLimit: 12 }, grid: { color: '#21262d' } },
        y: { ticks: { color: '#94a3b8', font: { size: 10 }, callback: v => formatBytes(v, 0) }, grid: { color: '#21262d' }, beginAtZero: true },
      },
    },
  });
}

function renderTrendsTrafficSummary(data) {
  const el = document.getElementById('trends-traffic-summary');
  if (!el) return;
  const rows = (data.summary || []);
  if (!rows.length) { el.innerHTML = '<tr><td colspan="5" class="loading">Keine Daten</td></tr>'; return; }
  el.innerHTML = rows.map(s => `
    <tr>
      <td><strong>${escapeHtml(s.iface_name)}</strong><br><span class="mono" style="color:var(--muted)">${escapeHtml(s.interface)}</span></td>
      <td class="rx-col">${formatBytes(s.rx_total)}</td>
      <td class="rx-col">${formatBytes(s.rx_avg)}</td>
      <td class="tx-col">${formatBytes(s.tx_total)}</td>
      <td class="tx-col">${formatBytes(s.tx_avg)}</td>
    </tr>
  `).join('');
}

function updateTrendsSummary() {
  // wird von den einzelnen Render-Funktionen gefüllt
}

function _formatBucketLabel(bucket, period) {
  if (period === '1yr') return bucket; // YYYY-MM
  if (period === '7d' && bucket.includes(' ')) {
    const [date, hour] = bucket.split(' ');
    const d = new Date(date + 'T00:00:00');
    return d.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit' }) + ' ' + hour + 'h';
  }
  // 30d -> YYYY-MM-DD
  const d = new Date(bucket + 'T00:00:00');
  return d.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit' });
}

// ── Feature 2: Monthly Traffic Report ─────────────────────────
async function loadTrafficReport() {
  const monthInput = document.getElementById('report-month');
  if (!monthInput) return;
  let month = monthInput.value;
  if (!month) {
    // Default: aktueller Monat
    const now = new Date();
    month = `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}`;
    monthInput.value = month;
  }
  const resultEl = document.getElementById('report-result');
  resultEl.textContent = 'Lade Bericht…';
  try {
    const data = await fetchJSON(`/api/trends/report?month=${month}`);
    renderTrafficReport(data);
    resultEl.textContent = '';
  } catch (e) {
    resultEl.textContent = `Fehler: ${e.message}`;
  }
}

function renderTrafficReport(data) {
  // Monatssummen
  const totalsEl = document.getElementById('report-totals');
  totalsEl.innerHTML = `
    <div class="stat-box"><div class="big-num" style="color:var(--green)">${formatBytes(data.month_rx_total)}</div><div class="big-label">Download Gesamt</div></div>
    <div class="stat-box"><div class="big-num" style="color:var(--accent)">${formatBytes(data.month_tx_total)}</div><div class="big-label">Upload Gesamt</div></div>
    <div class="stat-box"><div class="big-num" style="color:${data.rx_change_pct==null?'var(--muted)':data.rx_change_pct>0?'var(--red)':'var(--green)'}">${data.rx_change_pct==null?'—':(data.rx_change_pct>0?'+':'')+data.rx_change_pct+'%'}</div><div class="big-label">Δ DL Vormonat</div></div>
    <div class="stat-box"><div class="big-num" style="color:${data.tx_change_pct==null?'var(--muted)':data.tx_change_pct>0?'var(--red)':'var(--green)'}">${data.tx_change_pct==null?'—':(data.tx_change_pct>0?'+':'')+data.tx_change_pct+'%'}</div><div class="big-label">Δ UL Vormonat</div></div>
  `;

  // Interface-Tabelle
  const tbody = document.getElementById('report-interfaces-tbody');
  tbody.innerHTML = (data.comparison || []).length
    ? data.comparison.map(c => `
      <tr>
        <td><strong>${escapeHtml(c.iface_name)}</strong><br><span class="mono" style="color:var(--muted)">${escapeHtml(c.interface)}</span></td>
        <td class="rx-col">${formatBytes(c.rx_total)}</td>
        <td class="tx-col">${formatBytes(c.tx_total)}</td>
        <td style="color:var(--muted)">${formatBytes(c.prev_rx_total)}</td>
        <td style="color:var(--muted)">${formatBytes(c.prev_tx_total)}</td>
        <td style="color:${c.rx_change_pct==null?'var(--muted)':c.rx_change_pct>0?'var(--red)':'var(--green)'}">${c.rx_change_pct==null?'—':(c.rx_change_pct>0?'+':'')+c.rx_change_pct+'%'}</td>
        <td style="color:${c.tx_change_pct==null?'var(--muted)':c.tx_change_pct>0?'var(--red)':'var(--green)'}">${c.tx_change_pct==null?'—':(c.tx_change_pct>0?'+':'')+c.tx_change_pct+'%'}</td>
      </tr>
    `).join('')
    : '<tr><td colspan="7" class="loading">Keine Daten für diesen Monat</td></tr>';

  // Top Clients
  const clientsTbody = document.getElementById('report-top-clients-tbody');
  clientsTbody.innerHTML = (data.top_clients || []).length
    ? data.top_clients.map((c, i) => `
      <tr>
        <td>${i+1}</td>
        <td><strong>${escapeHtml(c.display)}</strong></td>
        <td class="mono">${escapeHtml(c.ip_address)}</td>
        <td class="rx-col">${formatBytes(c.rx_total)}</td>
        <td class="tx-col">${formatBytes(c.tx_total)}</td>
        <td>${formatBytes((c.rx_total||0)+(c.tx_total||0))}</td>
      </tr>
    `).join('')
    : '<tr><td colspan="6" class="loading" style="color:var(--muted)">Keine Client-Daten (nur 24h-Verlauf verfügbar)</td></tr>';

  // Tägliche Aufschlüsselung als Bar-Chart
  renderReportChart(data);
}

function renderReportChart(data) {
  const ctx = document.getElementById('chart-report');
  if (!ctx) return;
  if (reportChartInstance) reportChartInstance.destroy();

  // Tägliche Daten aggregieren (summiert über alle Interfaces)
  const dayMap = {};
  (data.daily || []).forEach(d => {
    if (!dayMap[d.date]) dayMap[d.date] = { rx: 0, tx: 0 };
    dayMap[d.date].rx += d.rx_bytes || 0;
    dayMap[d.date].tx += d.tx_bytes || 0;
  });
  const labels = Object.keys(dayMap).sort();
  reportChartInstance = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: labels.map(l => { const d = new Date(l+'T00:00:00'); return d.toLocaleDateString('de-DE',{day:'2-digit',month:'2-digit'}); }),
      datasets: [
        { label: '▼ Download', data: labels.map(l => dayMap[l].rx), backgroundColor: '#3fb950', borderRadius: 3 },
        { label: '▲ Upload', data: labels.map(l => dayMap[l].tx), backgroundColor: '#58a6ff', borderRadius: 3 },
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false, animation: { duration: 300 },
      plugins: { legend: { display: true, labels: { color: '#94a3b8', font: { size: 10 }, boxWidth: 10 } }, tooltip: { callbacks: { label: ctx => ` ${ctx.dataset.label}: ${formatBytes(ctx.parsed.y)}` } } },
      scales: {
        x: { ticks: { color: '#94a3b8', font: { size: 9 }, maxTicksLimit: 15 }, grid: { color: '#21262d' } },
        y: { ticks: { color: '#94a3b8', font: { size: 10 }, callback: v => formatBytes(v, 0) }, grid: { color: '#21262d' }, beginAtZero: true },
      },
    },
  });
}

// ── Init beim View-Wechsel ─────────────────────────────────────
async function initTrendsView() {
  if (!trendsLoaded) {
    trendsLoaded = true;
    // Event-Listener für Perioden-Buttons
    document.querySelectorAll('[data-trends-period]').forEach(btn => {
      btn.addEventListener('click', () => setTrendsPeriod(btn.dataset.trendsPeriod, btn));
    });
    // Event-Listener für Report-Monatswahl
    const reportBtn = document.getElementById('report-load');
    if (reportBtn) reportBtn.addEventListener('click', loadTrafficReport);
    // Ersten Bericht laden
    await loadTrafficReport();
  }
  await refreshTrends();
}

// Timer für Trends (nur im Trends-View aktiv)
let trendsTimer = null;
function startTrendsTimer() {
  if (trendsTimer) return;
  trendsTimer = setInterval(() => { if (currentView === 'trends') refreshTrends(); }, 120_000);
}

// Globale Referenz für app.js
window.initTrendsView = initTrendsView;
window.startTrendsTimer = startTrendsTimer;

// Auto-Init falls der View direkt per Hash aufgerufen wird
window.addEventListener('load', () => {
  // Perioden-Buttons initial aktiv setzen
  document.querySelectorAll('[data-trends-period]').forEach(btn => {
    if (btn.dataset.trendsPeriod === currentTrendsPeriod) btn.classList.add('active');
  });
  startTrendsTimer();
});