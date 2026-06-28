// ── Speedtest Integration ──────────────────────────────────────────
// Depends on: fetchJSON, escapeHtml, Chart.js

let speedtestRunning = false;
const speedtestChart = { instance: null };

async function refreshSpeedtestLast() {
  try {
    const data = await fetchJSON('/api/speedtest/last');
    renderSpeedtestResult(data);
  } catch (e) { console.warn('speedtest/last', e); }
}

async function refreshSpeedtestHistory() {
  try {
    const history = await fetchJSON('/api/speedtest/history?limit=50');
    renderSpeedtestChart(history);
  } catch (e) { console.warn('speedtest/history', e); }
}

function renderSpeedtestResult(data) {
  const dlEl = document.getElementById('speedtest-download');
  const ulEl = document.getElementById('speedtest-upload');
  const pingEl = document.getElementById('speedtest-ping');
  const timeEl = document.getElementById('speedtest-time');
  const ispEl = document.getElementById('speedtest-isp');
  if (!dlEl) return;

  if (!data || !data.available) {
    dlEl.textContent = '—';
    ulEl.textContent = '—';
    pingEl.textContent = '—';
    if (timeEl) timeEl.textContent = data?.message || 'Noch kein Test';
    if (ispEl) ispEl.textContent = '—';
    return;
  }

  dlEl.textContent = `${data.download_mbps.toFixed(1)} Mbps`;
  dlEl.style.color = 'var(--green)';
  ulEl.textContent = `${data.upload_mbps.toFixed(1)} Mbps`;
  ulEl.style.color = 'var(--accent)';
  pingEl.textContent = `${data.ping_ms.toFixed(0)} ms`;
  if (timeEl) timeEl.textContent = data.time || '—';
  if (ispEl) ispEl.textContent = data.isp ? `${escapeHtml(data.isp)}${data.server_name ? ' · ' + escapeHtml(data.server_name) : ''}` : '—';
}

async function runSpeedtest() {
  const btn = document.getElementById('speedtest-run-btn');
  const statusEl = document.getElementById('speedtest-status');
  if (speedtestRunning) return;
  speedtestRunning = true;
  if (btn) { btn.disabled = true; btn.textContent = '⏳ Läuft…'; }
  if (statusEl) { statusEl.textContent = 'Speedtest wird ausgeführt… dies kann 30–60 Sekunden dauern.'; statusEl.style.color = 'var(--yellow)'; }

  try {
    const r = await fetch(API + '/api/speedtest/run', { method: 'POST' });
    const data = await r.json();
    if (!data.ok) {
      if (statusEl) { statusEl.textContent = data.error || 'Speedtest fehlgeschlagen.'; statusEl.style.color = 'var(--red)'; }
    } else {
      if (statusEl) { statusEl.textContent = 'Speedtest abgeschlossen.'; statusEl.style.color = 'var(--green)'; }
      renderSpeedtestResult({
        available: true,
        time: new Date().toLocaleString('de-DE'),
        download_mbps: data.download_mbps,
        upload_mbps: data.upload_mbps,
        ping_ms: data.ping_ms,
        isp: data.isp || '',
        server_name: data.server_name || '',
      });
      refreshSpeedtestHistory();
    }
  } catch (e) {
    if (statusEl) { statusEl.textContent = `Fehler: ${e.message}`; statusEl.style.color = 'var(--red)'; }
  } finally {
    speedtestRunning = false;
    if (btn) { btn.disabled = false; btn.textContent = '▶ Starten'; }
  }
}

function renderSpeedtestChart(history) {
  const ctx = document.getElementById('chart-speedtest');
  if (!ctx) return;
  if (speedtestChart.instance) speedtestChart.instance.destroy();

  const labels = history.map(h => h.time || new Date(h.timestamp * 1000).toLocaleString('de-DE'));
  speedtestChart.instance = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [
        { label: '▼ Download (Mbps)', data: history.map(h => h.download_mbps), borderColor: '#22c55e', backgroundColor: 'rgba(34,197,94,.1)', borderWidth: 1.5, pointRadius: 2, fill: true, tension: 0.3 },
        { label: '▲ Upload (Mbps)', data: history.map(h => h.upload_mbps), borderColor: '#58a6ff', backgroundColor: 'rgba(88,166,255,.1)', borderWidth: 1.5, pointRadius: 2, fill: true, tension: 0.3 },
        { label: 'Ping (ms)', data: history.map(h => h.ping_ms), borderColor: '#f59e0b', backgroundColor: 'rgba(245,158,11,.08)', borderWidth: 1.5, pointRadius: 0, fill: false, tension: 0.3, yAxisID: 'y1' },
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false, animation: { duration: 300 },
      plugins: { legend: { display: true, labels: { color: '#8b949e', font: { size: 10 }, boxWidth: 12 } } },
      scales: {
        x: { ticks: { color: '#8b949e', font: { size: 9 }, maxTicksLimit: 8 }, grid: { color: '#21262d' } },
        y: { ticks: { color: '#8b949e', font: { size: 10 }, callback: v => v + ' Mbps' }, grid: { color: '#21262d' }, beginAtZero: true, title: { display: true, text: 'Mbps', color: '#8b949e', font: { size: 10 } } },
        y1: { position: 'right', ticks: { color: '#f59e0b', font: { size: 10 }, callback: v => v + ' ms' }, grid: { display: false }, beginAtZero: true, title: { display: true, text: 'ms', color: '#f59e0b', font: { size: 10 } } },
      },
    },
  });
}

function speedtestInit() {
  const btn = document.getElementById('speedtest-run-btn');
  if (btn) btn.addEventListener('click', runSpeedtest);
  refreshSpeedtestLast();
  refreshSpeedtestHistory();
}

document.addEventListener('DOMContentLoaded', () => setTimeout(speedtestInit, 300));