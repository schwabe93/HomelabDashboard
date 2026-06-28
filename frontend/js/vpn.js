// ── VPN Status (WireGuard / OpenVPN) ───────────────────────────────
// Depends on: fetchJSON, escapeHtml, formatBytes (utils.js / app.js)

let vpnData = { wireguard: null, openvpn: null };

async function refreshVpn() {
  await Promise.allSettled([refreshWireguard(), refreshOpenvpn()]);
}

async function refreshWireguard() {
  try {
    vpnData.wireguard = await fetchJSON('/api/vpn/wireguard');
    renderWireguard();
  } catch (e) { console.warn('vpn/wireguard', e); }
}

async function refreshOpenvpn() {
  try {
    vpnData.openvpn = await fetchJSON('/api/vpn/openvpn');
    renderOpenvpn();
  } catch (e) { console.warn('vpn/openvpn', e); }
}

function renderWireguard() {
  const data = vpnData.wireguard;
  const body = document.getElementById('vpn-wg-body');
  if (!body || !data) return;

  if (!data.available) {
    body.innerHTML = `<div class="banner" style="display:flex">⚠️ ${escapeHtml(data.error || 'WireGuard nicht verfügbar.')}</div>`;
    return;
  }

  const active = data.active_peers || 0;
  const total = data.total_peers || 0;
  const rx = data.data_transferred?.rx || 0;
  const tx = data.data_transferred?.tx || 0;

  let html = `
    <div class="ipdhcp-summary">
      <div class="stat-box"><div class="big-num" style="color:var(--green)">${active}</div><div class="big-label">Aktive Peers</div></div>
      <div class="stat-box"><div class="big-num">${total}</div><div class="big-label">Peers Gesamt</div></div>
      <div class="stat-box"><div class="big-num" style="color:var(--green);font-size:18px">${formatBytes(rx)}</div><div class="big-label">▼ Empfangen</div></div>
      <div class="stat-box"><div class="big-num" style="color:var(--accent);font-size:18px">${formatBytes(tx)}</div><div class="big-label">▲ Gesendet</div></div>
    </div>`;

  if (data.peers && data.peers.length) {
    html += `<div class="section-label">Peers</div><div class="scroll-y" style="max-height:240px"><div class="table-wrap"><table>
      <thead><tr><th>Name</th><th>Endpoint</th><th>Status</th><th>Handshake</th><th>▼ RX</th><th>▲ TX</th></tr></thead><tbody>`;
    html += data.peers.map(p => {
      const statusColor = p.active ? 'var(--green)' : (p.enabled ? 'var(--yellow)' : 'var(--muted)');
      const statusText = p.active ? 'Aktiv' : (p.enabled ? 'Inaktiv' : 'Deaktiviert');
      return `<tr>
        <td><strong>${escapeHtml(p.name || '—')}</strong></td>
        <td class="mono">${escapeHtml(p.endpoint || '—')}</td>
        <td><span style="color:${statusColor}">${statusText}</span></td>
        <td class="mono">${escapeHtml(p.last_handshake || '—')}</td>
        <td class="rx-col">${formatBytes(p.rx_bytes)}</td>
        <td class="tx-col">${formatBytes(p.tx_bytes)}</td>
      </tr>`;
    }).join('');
    html += `</tbody></table></div></div>`;
  } else {
    html += '<div class="loading">Keine WireGuard-Peers konfiguriert.</div>';
  }

  body.innerHTML = html;
}

function renderOpenvpn() {
  const data = vpnData.openvpn;
  const body = document.getElementById('vpn-ovpn-body');
  if (!body || !data) return;

  if (!data.available) {
    body.innerHTML = `<div class="banner" style="display:flex">⚠️ ${escapeHtml(data.error || 'OpenVPN nicht verfügbar.')}</div>`;
    return;
  }

  const connected = data.connected_clients || 0;
  const total = data.total_clients || 0;
  const rx = data.data_transferred?.rx || 0;
  const tx = data.data_transferred?.tx || 0;

  let html = `
    <div class="ipdhcp-summary">
      <div class="stat-box"><div class="big-num" style="color:var(--green)">${connected}</div><div class="big-label">Verbunden</div></div>
      <div class="stat-box"><div class="big-num">${total}</div><div class="big-label">Clients Gesamt</div></div>
      <div class="stat-box"><div class="big-num" style="color:var(--green);font-size:18px">${formatBytes(rx)}</div><div class="big-label">▼ Empfangen</div></div>
      <div class="stat-box"><div class="big-num" style="color:var(--accent);font-size:18px">${formatBytes(tx)}</div><div class="big-label">▲ Gesendet</div></div>
    </div>`;

  const allClients = [...(data.servers || []), ...(data.clients || [])];
  if (allClients.length) {
    html += `<div class="section-label">Verbindungen</div><div class="scroll-y" style="max-height:240px"><div class="table-wrap"><table>
      <thead><tr><th>Name</th><th>Typ</th><th>Status</th><th>Real Address</th><th>Virt. Address</th><th>▼ RX</th><th>▲ TX</th></tr></thead><tbody>`;
    html += allClients.map((c, i) => {
      const isServer = i < (data.servers?.length || 0);
      const statusColor = c.connected ? 'var(--green)' : (c.enabled ? 'var(--muted)' : 'var(--muted)');
      const statusText = c.connected ? 'Verbunden' : (c.enabled ? 'Getrennt' : 'Deaktiviert');
      return `<tr>
        <td><strong>${escapeHtml(c.name || c.common_name || '—')}</strong></td>
        <td>${isServer ? 'Server' : 'Client'}</td>
        <td><span style="color:${statusColor}">${statusText}</span></td>
        <td class="mono">${escapeHtml(c.real_address || '—')}</td>
        <td class="mono">${escapeHtml(c.virtual_address || '—')}</td>
        <td class="rx-col">${formatBytes(c.rx_bytes)}</td>
        <td class="tx-col">${formatBytes(c.tx_bytes)}</td>
      </tr>`;
    }).join('');
    html += `</tbody></table></div></div>`;
  } else {
    html += '<div class="loading">Keine OpenVPN-Verbindungen.</div>';
  }

  body.innerHTML = html;
}

function vpnInit() {
  refreshVpn();
}

document.addEventListener('DOMContentLoaded', () => setTimeout(vpnInit, 300));
setInterval(refreshVpn, 60_000);