function formatBytes(bytes, decimals = 1) {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(decimals)) + ' ' + sizes[i];
}

function formatBits(bps) {
  if (bps === 0) return '0 bps';
  const k = 1000;
  const sizes = ['bps', 'Kbps', 'Mbps', 'Gbps'];
  const i = Math.floor(Math.log(Math.max(bps, 1)) / Math.log(k));
  return parseFloat((bps / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

function formatUptime(s) {
  if (!s) return '—';
  // e.g. "1+06:01:03"
  if (s.includes('+')) {
    const [days, time] = s.split('+');
    const [h] = time.split(':');
    return `${days}d ${h}h`;
  }
  const parts = s.split(':');
  if (parts.length === 3) return `${parts[0]}h ${parts[1]}m`;
  return s;
}

function tsToTime(ts) {
  return new Date(ts * 1000).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });
}

function pct(used, total) {
  if (!total) return 0;
  return Math.round((used / total) * 100);
}

function gauge(value, max = 100) {
  const p = Math.min(100, Math.round((value / max) * 100));
  let color = '#00c950';
  if (p > 80) color = '#ff4757';
  else if (p > 60) color = '#ffa502';
  return `<div class="gauge-bar"><div class="gauge-fill" style="width:${p}%;background:${color}"></div></div>`;
}
