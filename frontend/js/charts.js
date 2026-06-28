const CHART_DEFAULTS = {
  responsive: true,
  maintainAspectRatio: false,
  animation: { duration: 300 },
  plugins: { legend: { display: false } },
  scales: {
    x: {
      type: 'linear',
      ticks: {
        color: '#8b949e',
        maxTicksLimit: 6,
        callback: v => tsToTime(v),
        font: { size: 10 },
      },
      grid: { color: '#21262d' },
    },
    y: {
      ticks: { color: '#8b949e', font: { size: 10 }, callback: v => formatBits(v) },
      grid: { color: '#21262d' },
      beginAtZero: true,
    },
  },
};

const ifaceCharts = {};
const systemChart = { instance: null };

function getOrCreateIfaceChart(canvasId) {
  if (ifaceCharts[canvasId]) return ifaceCharts[canvasId];
  const ctx = document.getElementById(canvasId);
  if (!ctx) return null;
  ifaceCharts[canvasId] = new Chart(ctx, {
    type: 'line',
    data: {
      datasets: [
        { label: 'RX', data: [], borderColor: '#3fb950', backgroundColor: 'rgba(63,185,80,.1)', borderWidth: 1.5, pointRadius: 0, fill: true, tension: 0.3 },
        { label: 'TX', data: [], borderColor: '#58a6ff', backgroundColor: 'rgba(88,166,255,.1)', borderWidth: 1.5, pointRadius: 0, fill: true, tension: 0.3 },
      ],
    },
    options: { ...CHART_DEFAULTS },
  });
  return ifaceCharts[canvasId];
}

function updateIfaceChart(canvasId, history) {
  const chart = getOrCreateIfaceChart(canvasId);
  if (!chart) return;
  chart.data.datasets[0].data = history.map(p => ({ x: p.ts, y: p.rx }));
  chart.data.datasets[1].data = history.map(p => ({ x: p.ts, y: p.tx }));
  chart.update('none');
}

function getOrCreateSystemChart() {
  if (systemChart.instance) return systemChart.instance;
  const ctx = document.getElementById('chart-system');
  if (!ctx) return null;
  systemChart.instance = new Chart(ctx, {
    type: 'line',
    data: {
      datasets: [
        { label: 'CPU %', data: [], borderColor: '#f85149', backgroundColor: 'rgba(248,81,73,.08)', borderWidth: 1.5, pointRadius: 0, fill: true, tension: 0.3, yAxisID: 'y' },
        { label: 'RAM %', data: [], borderColor: '#bc8cff', backgroundColor: 'rgba(188,140,255,.08)', borderWidth: 1.5, pointRadius: 0, fill: true, tension: 0.3, yAxisID: 'y' },
      ],
    },
    options: {
      ...CHART_DEFAULTS,
      plugins: { legend: { display: true, labels: { color: '#8b949e', font: { size: 10 }, boxWidth: 12 } } },
      scales: {
        x: { ...CHART_DEFAULTS.scales.x },
        y: { ticks: { color: '#8b949e', font: { size: 10 }, callback: v => v + '%' }, grid: { color: '#21262d' }, min: 0, max: 100, beginAtZero: true },
      },
    },
  });
  return systemChart.instance;
}

function updateSystemChart(history) {
  const chart = getOrCreateSystemChart();
  if (!chart) return;
  chart.data.datasets[0].data = history.map(p => ({ x: p.ts, y: p.cpu_pct }));
  chart.data.datasets[1].data = history.map(p => ({ x: p.ts, y: p.mem_pct }));
  chart.update('none');
}

// ── Traffic bar chart ──────────────────────────────────────────
const trafficChart = { instance: null };

const IFACE_COLORS = {
  pppoe0:  { rx: '#f0883e', tx: 'rgba(240,136,62,.4)' },
  vtnet2:  { rx: '#bc8cff', tx: 'rgba(188,140,255,.4)' },
  vtnet0:  { rx: '#58a6ff', tx: 'rgba(88,166,255,.4)' },
  vtnet1:  { rx: '#3fb950', tx: 'rgba(63,185,80,.4)' },
  default: { rx: '#8b949e', tx: 'rgba(139,148,158,.4)' },
};

function buildTrafficChart(labels, datasets) {
  const ctx = document.getElementById('chart-traffic');
  if (!ctx) return;
  if (trafficChart.instance) trafficChart.instance.destroy();
  trafficChart.instance = new Chart(ctx, {
    type: 'bar',
    data: { labels, datasets },
    options: {
      responsive: true, maintainAspectRatio: false,
      animation: { duration: 300 },
      plugins: {
        legend: { display: true, labels: { color: '#8b949e', font: { size: 10 }, boxWidth: 10 } },
        tooltip: {
          callbacks: {
            label: ctx => ` ${ctx.dataset.label}: ${formatBytes(ctx.parsed.y)}`,
          },
        },
      },
      scales: {
        x: {
          ticks: { color: '#8b949e', font: { size: 10 }, maxTicksLimit: 12 },
          grid: { color: '#21262d' },
          stacked: false,
        },
        y: {
          ticks: { color: '#8b949e', font: { size: 10 }, callback: v => formatBytes(v, 0) },
          grid: { color: '#21262d' },
          beginAtZero: true,
        },
      },
    },
  });
}

const sparkCharts = {};

// ── Starlink charts ──
const starlinkLatencyChart = { instance: null };
const starlinkThroughputChart = { instance: null };

function updateStarlinkLatencyChart(latencyMs, dropRate) {
  const ctx = document.getElementById('chart-starlink-latency');
  if (!ctx) return;
  if (starlinkLatencyChart.instance) starlinkLatencyChart.instance.destroy();

  const labels = latencyMs.map((_, i) => i);
  const datasets = [
    {
      label: 'Latenz (ms)',
      data: latencyMs,
      borderColor: '#38bdf8',
      backgroundColor: 'rgba(56,189,248,.1)',
      borderWidth: 1.5, pointRadius: 0, fill: true, tension: 0.3,
      yAxisID: 'y',
    },
  ];
  if (dropRate && dropRate.length) {
    datasets.push({
      label: 'Drop Rate (%)',
      data: dropRate.map(d => d != null ? d * 100 : 0),
      borderColor: '#ef4444',
      backgroundColor: 'rgba(239,68,68,.1)',
      borderWidth: 1.5, pointRadius: 0, fill: false, tension: 0.3,
      yAxisID: 'y1',
    });
  }

  starlinkLatencyChart.instance = new Chart(ctx, {
    type: 'line',
    data: { labels, datasets },
    options: {
      responsive: true, maintainAspectRatio: false, animation: { duration: 300 },
      plugins: { legend: { display: true, labels: { color: '#94a3b8', font: { size: 10 }, boxWidth: 12 } } },
      scales: {
        x: { ticks: { color: '#94a3b8', font: { size: 9 }, maxTicksLimit: 8 }, grid: { color: '#21262d' } },
        y: { ticks: { color: '#94a3b8', font: { size: 10 } }, grid: { color: '#21262d' }, beginAtZero: true, title: { display: true, text: 'ms', color: '#94a3b8', font: { size: 10 } } },
        y1: { position: 'right', ticks: { color: '#ef4444', font: { size: 10 }, callback: v => v + '%' }, grid: { display: false }, beginAtZero: true, max: 100, title: { display: true, text: '%', color: '#ef4444', font: { size: 10 } } },
      },
    },
  });
}

function updateStarlinkThroughputChart(downlink, uplink) {
  const ctx = document.getElementById('chart-starlink-throughput');
  if (!ctx) return;
  if (starlinkThroughputChart.instance) starlinkThroughputChart.instance.destroy();

  const labels = downlink.map((_, i) => i);
  starlinkThroughputChart.instance = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [
        { label: '▼ Download', data: downlink, borderColor: '#22c55e', backgroundColor: 'rgba(34,197,94,.1)', borderWidth: 1.5, pointRadius: 0, fill: true, tension: 0.3 },
        { label: '▲ Upload', data: uplink, borderColor: '#818cf8', backgroundColor: 'rgba(129,140,248,.1)', borderWidth: 1.5, pointRadius: 0, fill: true, tension: 0.3 },
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false, animation: { duration: 300 },
      plugins: { legend: { display: true, labels: { color: '#94a3b8', font: { size: 10 }, boxWidth: 12 } } },
      scales: {
        x: { ticks: { color: '#94a3b8', font: { size: 9 }, maxTicksLimit: 8 }, grid: { color: '#21262d' } },
        y: { ticks: { color: '#94a3b8', font: { size: 10 }, callback: v => formatBits(v, 0) }, grid: { color: '#21262d' }, beginAtZero: true },
      },
    },
  });
}

function updateSparkline(canvasId, history) {
  const ctx = document.getElementById(canvasId);
  if (!ctx) return;
  if (sparkCharts[canvasId]) sparkCharts[canvasId].destroy();
  sparkCharts[canvasId] = new Chart(ctx, {
    type: 'line',
    data: {
      datasets: [
        { data: history.map(p => ({ x: p.ts, y: p.rx })), borderColor: '#3fb950', borderWidth: 1.5, pointRadius: 0, fill: false, tension: 0.3 },
        { data: history.map(p => ({ x: p.ts, y: p.tx })), borderColor: '#58a6ff', borderWidth: 1.5, pointRadius: 0, fill: false, tension: 0.3 },
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false, animation: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { type: 'linear', display: false },
        y: { display: false, beginAtZero: true },
      },
    },
  });
}
