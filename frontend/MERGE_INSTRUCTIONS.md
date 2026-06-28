# Merge Instructions — 6 neue Features

Alle Änderungen, die in den **bestehenden** Dateien `index.html`, `app.js` und `main.py` vorgenommen werden müssen, um die sechs neuen Features zu aktivieren. Alle neuen Dateien wurden bereits angelegt und benötigen keine weiteren Anpassungen.

---

## 1. `backend/main.py` — Router-Importe & Registrierung

### Import-Zeile (vorhandene Zeile 10 ergänzen)

**Vorhanden:**
```python
from routers import system, interfaces, clients, firewall, hosts, gateways, dns, wan, traffic, ipdhcp, starlink
```

**Ersetzen durch:**
```python
from routers import (
    system, interfaces, clients, firewall, hosts, gateways, dns, wan, traffic,
    ipdhcp, starlink, device_labels, docker_status, proxmox, uptime_kuma,
)
```

### Router-Registrierung (nach Zeile 42, vor `app.mount(...)`)

```python
app.include_router(device_labels.router, prefix="/api")
app.include_router(docker_status.router,  prefix="/api")
app.include_router(proxmox.router,        prefix="/api")
app.include_router(uptime_kuma.router,    prefix="/api")
```

---

## 2. `frontend/index.html`

### 2.1 `<head>` — Manifest + Theme-Light-CSS

Nach Zeile 7 (`<link rel="stylesheet" href="css/dashboard.css">`) einfügen:

```html
<link rel="manifest" href="manifest.json">
<link rel="stylesheet" href="css/theme-light.css">
```

### 2.2 Header — Theme-Toggle & PWA-Install Button

Die Buttons werden automatisch von `js/theme.js` bzw. `js/pwa.js` in den Header eingefügt. Es ist **keine** manuelle HTML-Änderung im `<div id="header">` nötig.

### 2.3 Nav-Tabs — neue Bereiche

In der `<nav class="app-tabs">` (Zeile 56–60) nach dem Starlink-Button ergänzen:

```html
<button class="app-tab" type="button" data-view-target="docker">🐳 Docker</button>
<button class="app-tab" type="button" data-view-target="proxmox">💻 Proxmox</button>
<button class="app-tab" type="button" data-view-target="uptime-kuma">📡 Uptime Kuma</button>
```

### 2.4 Neue Views — als neue `<section>` innerhalb von `<main class="app-main">`

Nach dem schließenden `</section>` des Starlink-Views (vor `</main>`) einfügen:

```html
<!-- ── Docker View ── -->
<section class="app-view" data-view="docker" hidden>
  <header class="page-header">
    <div>
      <div class="eyebrow">Unraid Container</div>
      <h2>Docker Status</h2>
      <p>Container-Übersicht von Unraid mit CPU-, Speicher- und Health-Status.</p>
    </div>
  </header>
  <div class="grid">
    <div class="card grid-full" data-view="docker">
      <div class="card-header">
        🐳 Docker Container
        <span class="badge" id="docker-count">—</span>
        <button class="tab-btn" type="button" id="docker-refresh">Aktualisieren</button>
      </div>
      <div class="card-body">
        <div class="banner" id="docker-errors" style="display:none"></div>
        <div class="scroll-y" style="max-height:520px">
          <div class="table-wrap">
            <table>
              <thead><tr><th>Name</th><th>Image</th><th>Status</th><th>CPU</th><th>Speicher</th><th>Uptime</th><th>Ports</th></tr></thead>
              <tbody id="docker-tbody"><tr><td colspan="7" class="loading">Lade Container…</td></tr></tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  </div>
</section>

<!-- ── Proxmox View ── -->
<section class="app-view" data-view="proxmox" hidden>
  <header class="page-header">
    <div>
      <div class="eyebrow">Virtualisierung</div>
      <h2>Proxmox VM/CT</h2>
      <p>Übersicht aller virtuellen Maschinen und LXC-Container mit Start/Stop-Steuerung.</p>
    </div>
  </header>
  <div class="grid">
    <div class="card grid-full" data-view="proxmox">
      <div class="card-header">
        💻 VMs & Container
        <span class="badge" id="proxmox-count">—</span>
        <button class="tab-btn" type="button" id="proxmox-refresh">Aktualisieren</button>
      </div>
      <div class="card-body">
        <div class="banner" id="proxmox-errors" style="display:none"></div>
        <div class="scroll-y" style="max-height:520px">
          <div class="table-wrap">
            <table>
              <thead><tr><th>ID</th><th>Name</th><th>Typ</th><th>Status</th><th>Cores</th><th>Speicher</th><th>Aktion</th></tr></thead>
              <tbody id="proxmox-tbody"><tr><td colspan="7" class="loading">Lade VMs/CTs…</td></tr></tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  </div>
</section>

<!-- ── Uptime Kuma View ── -->
<section class="app-view" data-view="uptime-kuma" hidden>
  <header class="page-header">
    <div>
      <div class="eyebrow">Monitoring</div>
      <h2>Uptime Kuma</h2>
      <p>Status aller überwachten Dienste mit Uptime-Prozent und Antwortzeit.</p>
    </div>
  </header>
  <div class="grid">
    <div class="card grid-full" data-view="uptime-kuma">
      <div class="card-header">
        📡 Monitore
        <button class="tab-btn" type="button" id="uptime-kuma-refresh">Aktualisieren</button>
      </div>
      <div class="card-body">
        <div class="banner" id="uptime-kuma-errors" style="display:none"></div>
        <div class="ipdhcp-summary" id="uptime-kuma-summary" style="margin-bottom:14px"></div>
        <div class="grid" id="uptime-kuma-grid" style="grid-template-columns:repeat(auto-fill,minmax(240px,1fr))">
          <div class="loading">Lade Monitore…</div>
        </div>
      </div>
    </div>
  </div>
</section>
```

### 2.5 Script-Tags — am Ende von `<body>`

Vorhandene Script-Tags (Zeilen 416–419) bleiben. Danach ergänzen:

```html
<script src="js/theme.js?v=2"></script>
<script src="js/pwa.js?v=2"></script>
<script src="js/device_labels.js?v=2"></script>
<script src="js/docker_status.js?v=2"></script>
<script src="js/proxmox.js?v=2"></script>
<script src="js/uptime_kuma.js?v=2"></script>
```

---

## 3. `frontend/js/app.js`

### 3.1 Views registrieren

**Vorhanden (Zeile 16):**
```js
const VALID_VIEWS = new Set(['dashboard', 'ip-management', 'starlink']);
```

**Ersetzen durch:**
```js
const VALID_VIEWS = new Set(['dashboard', 'ip-management', 'starlink', 'docker', 'proxmox', 'uptime-kuma']);
```

**Vorhanden (Zeile 17–21):**
```js
const VIEW_TITLES = {
  dashboard: 'Dashboard',
  'ip-management': 'IP Management',
  starlink: 'Starlink',
};
```

**Ersetzen durch:**
```js
const VIEW_TITLES = {
  dashboard: 'Dashboard',
  'ip-management': 'IP Management',
  starlink: 'Starlink',
  docker: 'Docker',
  proxmox: 'Proxmox',
  'uptime-kuma': 'Uptime Kuma',
};
```

### 3.2 Lazy-Loading der neuen Views in `setView()`

In der Funktion `setView()` (nach dem `starlink`-Block, ca. Zeile 68) ergänzen:

```js
  if (target === 'docker' && !dockerLoaded) { dockerLoaded = true; DockerStatus.init(); }
  if (target === 'proxmox' && !proxmoxLoaded) { proxmoxLoaded = true; Proxmox.refresh(); }
  if (target === 'uptime-kuma' && !uptimeKumaLoaded) { uptimeKumaLoaded = true; UptimeKuma.refresh(); }
```

Und am Dateianfang bei den State-Variablen (ca. Zeile 13) ergänzen:

```js
let dockerLoaded = false;
let proxmoxLoaded = false;
let uptimeKumaLoaded = false;
```

> Hinweis: Die Auto-Refresh-Timer der neuen Module starten automatisch beim Initialisieren. Die Module registrieren sich selbst auf `DOMContentLoaded`; das lazy-Init oben verhindert doppelte Timer nur, wenn der View aktiviert wird.

### 3.3 Device-Labels in Tabellen einbinden

In `refreshClients()` die Geräte-Spalte anpassen. **Vorhanden (Zeile 258):**
```js
        <td><strong>${c.display || '—'}</strong></td>
```
**Ersetzen durch:**
```js
        <td><strong>${window.DeviceLabels ? DeviceLabels.display(c.mac, c.display) : (c.display || '—')}</strong></td>
```

In `refreshHosts()` die Hostname-Spalte anpassen. **Vorhanden (Zeile 324):**
```js
      `<tr><td class="mono">${h.ip}</td><td class="mono">${h.mac}</td><td>${h.hostname || h.manufacturer || '<span style="color:var(--muted)">—</span>'}</td><td class="mono">${h.interface}</td></tr>`
```
**Ersetzen durch:**
```js
      `<tr><td class="mono">${h.ip}</td><td class="mono">${h.mac}</td><td>${window.DeviceLabels ? DeviceLabels.display(h.mac, h.hostname || h.manufacturer) : (h.hostname || h.manufacturer || '<span style="color:var(--muted)">—</span>')}</td><td class="mono">${h.interface}</td></tr>`
```

Optional: einen Edit-Button in jede Zeile einbauen. Beispiel für die Clients-Tabelle — nach dem `</td>` der MAC-Spalte ergänzen:
```js
        <td>${window.DeviceLabels ? '' : ''}<button class="tab-btn" type="button" onclick="DeviceLabels.openEditor('${c.mac}','${c.display||''}',refreshClients)">✏️</button></td>
```
(Dafür muss die `colspan` der Loading-Zeile von 7 auf 8 erhöht werden.)

---

## 4. Environment-Variablen (optional, `.env`)

Proxmox-Standard-Password ist bereits im Code hinterlegt (`Dachgeschoss93!`), kann aber überschrieben werden:

```
PROXMOX_HOST=192.168.188.20
PROXMOX_USER=root
PROXMOX_PASSWORD=Dachgeschoss93!
PROXMOX_SSH_MODE=auto

UPTIME_KUMA_HOST=192.168.188.106
UPTIME_KUMA_PORT=3001
UPTIME_KUMA_STATUS_SLUG=default
```

---

## 5. Übersicht der neuen Dateien

| Feature | Neue Dateien |
|---|---|
| 1. Theme-Toggle | `frontend/css/theme-light.css`, `frontend/js/theme.js` |
| 2. PWA | `frontend/manifest.json`, `frontend/sw.js`, `frontend/js/pwa.js` |
| 3. Device Labels | `backend/routers/device_labels.py`, `frontend/js/device_labels.js` |
| 4. Docker Status | `backend/routers/docker_status.py`, `frontend/js/docker_status.js` |
| 5. Proxmox | `backend/routers/proxmox.py`, `frontend/js/proxmox.js` |
| 6. Uptime Kuma | `backend/routers/uptime_kuma.py`, `frontend/js/uptime_kuma.js` |

Keine der oben genannten Dateien verändert bestehenden Code — sie werden nur geladen. Die einzigen Editoren bestehen in `index.html`, `app.js` und `main.py` wie oben beschrieben.