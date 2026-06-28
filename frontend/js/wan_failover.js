// ── Multi-WAN Failover Visualization ───────────────────────────────
// Depends on: fetchJSON, escapeHtml, Chart.js

let failoverData = null;
let failoverHistory = [];
const failoverTimelineChart = { instance: null };

async function refreshFailover() {
  try {
    failoverData = await fetchJSON('/api/wan/failover');
    renderFailover();
  } catch (e) { console.warn('wan/failover', e); }
}

async function refreshFailoverHistory() {
  try {
    const data = await fetchJSON('/api/wan/failover/history?limit=50');
    failoverHistory = data.events || [];
    renderFailoverTimeline();
    renderFailoverEvents();
  } catch (e) { console.warn('wan/failover/history', e); }
}

function renderFailover() {
  const body = document.getElementById('wan-failover-body');
  if (!body || !failoverData) return;

  const gws = failoverData.gateways || [];
  const active = failoverData.current_active_wan;
  const standby = failoverData.current_standby;
  const lastFailover = failoverData.last_failover_time_str || '—';
  const count24h = failoverData.failover_count_24h || 0;

  // Side-by-side WAN cards
  let html = '<div class="wan-failover-cards">';
  for (const gw of gws) {
    const isActive = gw.role === 'active';
    const isStandby = gw.role === 'standby';
    const cardClass = isActive ? 'wan-card-active' : (isStandby ? 'wan-card-standby' : 'wan-card-other');
    const statusColor = gw.online ? 'var(--green)' : 'var(--red)';
    const roleText = isActive ? 'AKTIV' : (isStandby ? 'STANDBY' : '—');
    html += `<div class="wan-failover-card ${cardClass}">
      <div class="wan-card-header">
        <span class="dot" style="background:${statusColor};box-shadow:0 0 6px ${statusColor}"></span>
        <span class="wan-card-label">${escapeHtml(gw.label)}</span>
        <span class="wan-card-role" style="color:${isActive ? 'var(--green)' : 'var(--muted)'}">${roleText}</span>
      </div>
      <div class="wan-card-name">${escapeHtml(gw.name)}</div>
      <div class="wan-card-stats">
        <span>Status: <strong style="color:${statusColor}">${escapeHtml(gw.status)}</strong></span>
        <span>Delay: <span class="mono">${escapeHtml(gw.delay)}</span></span>
        <span>Loss: <span class="mono">${escapeHtml(gw.loss)}</span></span>
      </div>
    </div>`;
  }
  if (!gws.length) {
    html += '<div class="loading">Keine Gateway-Daten verfügbar.</div>';
  }
  html += '</div>';

  // Summary stats
  html += `<div class="ipdhcp-summary" style="margin-top:12px">
    <div class="stat-box"><div class="big-num" style="color:var(--green)">${escapeHtml(active || '—')}</div><div class="big-label">Aktiver WAN</div></div>
    <div class="stat-box"><div class="big-num" style="color:var(--muted)">${escapeHtml(standby || '—')}</div><div class="big-label">Standby WAN</div></div>
    <div class="stat-box"><div class="big-num" style="color:var(--accent);font-size:16px">${escapeHtml(lastFailover)}</div><div class="big-label">Letzter Failover</div></div>
    <div class="stat-box"><div class="big-num" style="color:${count24h > 0 ? 'var(--yellow)' : 'var(--green)'}">${count24h}</div><div class="big-label">Failovers (24h)</div></div>
  </div>`;

  body.innerHTML = html;
}

function renderFailoverEvents() {
  const tbody = document.getElementById('wan-failover-events-tbody');
  if (!tbody) return;
  if (!failoverHistory.length) {
    tbody.innerHTML = '<tr><td colspan="4" class="loading">Keine Failover-Ereignisse.</td></tr>';
    return;
  }
  tbody.innerHTML = failoverHistory.map(ev => {
    return `<tr>
      <td class="mono">${escapeHtml(ev.time)}</td>
      <td class="mono" style="color:var(--red)">${escapeHtml(ev.from_wan || '—')}</td>
      <td style="text-align:center;color:var(--muted)">→</td>
      <td class="mono" style="color:var(--green)">${escapeHtml(ev.to_wan || '—')}</td>
    </tr>`;
  }).join('');
}

function renderFailoverTimeline() {
  const ctx = document.getElementById('chart-wan-failover-timeline');
  if (!ctx) return;
  if (failoverTimelineChart.instance) failoverTimelineChart.instance.destroy();

  // Build a timeline bar chart: each event is a point; bar color indicates which WAN was active
  // We reverse history to chronological order
  const events = [...failoverHistory].reverse();
  if (!events.length) {
    // Show a flat "no events" chart
    failoverTimelineChart.instance = new Chart(ctx, {
      type: 'bar',
      data: { labels: ['Keine Ereignisse'], datasets: [{ label: 'Failovers', data: [0], backgroundColor: 'rgba(148,163,184,.2)' }] },
      options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { ticks: { color: '#8b949e' } }, y: { display: false, beginAtZero: true } } },
    });
    return;
  }

  const labels = events.map(ev => ev.time);
  // Encode events as numeric: each event = 1; color by destination WAN
  const wanColors = {};
  function colorFor(wan) {
    if (!wan) return 'rgba(148,163,184,.4)';
    if (wan.toLowerCase().includes('starlink')) return '#38bdf8';
    if (wan.toLowerCase().includes('wan')) return '#22c55e';
    return '#bc8cff';
  }
  const colors = events.map(ev => colorFor(ev.to_wan));
  const data = events.map(() => 1);

  failoverTimelineChart.instance = new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        label: 'Failover-Ereignis',
        data,
        backgroundColor: colors,
        borderRadius: 3,
        borderSkipped: false,
      }],
    },
    options: {
      responsive: true, maintainAspectRatio: false, animation: { duration: 300 },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: ctx => {
              const ev = events[ctx.dataIndex];
              return ` ${ev.from_wan || '—'} → ${ev.to_wan || '—'}`;
            },
          },
        },
      },
      scales: {
        x: { ticks: { color: '#8b949e', font: { size: 9 }, maxTicksLimit: 10 }, grid: { color: '#21262d' } },
        y: { display: false, beginAtZero: true, max: 2 },
      },
    },
  });
}

function wanFailoverInit() {
  refreshFailover();
  refreshFailoverHistory();
}

document.addEventListener('DOMContentLoaded', () => setTimeout(wanFailoverInit, 300));
setInterval(refreshFailover, 30_000);
setInterval(refreshFailoverHistory, 120_000);