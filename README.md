# 🏠 Homelab Dashboard

Self-hosted Monitoring Dashboard für OPNsense — läuft auf Ubuntu Server, zeigt Echtzeit-Netzwerkstatistiken, per-Client Bandbreite und Systemmetriken.

![Stack](https://img.shields.io/badge/Stack-FastAPI%20%2B%20Chart.js-blue)
![Python](https://img.shields.io/badge/Python-3.12+-green)
![License](https://img.shields.io/badge/License-MIT-gray)

---

## 📸 Features

| Widget | Beschreibung |
|--------|-------------|
| **Gateway Status** | WAN + STARLINK Latenz, Paketverlust, Online/Offline |
| **WAN IPs** | Aktuelle externe IP-Adressen aller Uplinks im Header |
| **Interface Traffic** | Echtzeit RX/TX pro Interface als Linienchart (1h) |
| **Download/Upload Statistik** | Heute / Woche / Monat / Jahr als Balkendiagramm |
| **Per-Client Bandwidth** | Wer verbraucht wie viel (via OPNsense NetFlow/Insight) |
| **Firewall States** | Aktive Verbindungen + Top Quell-IPs |
| **Top Blocked IPs** | Meistgeblockte Quell-IPs der letzten Stunde |
| **Unbound DNS** | Anfragen, Cache-Hit-Rate, Ø Auflösungszeit |
| **Interface Fehler** | Input/Output Errors + Queue Drops |
| **System Health** | CPU%, RAM, Load Average — 6h Verlauf |
| **Geräte im Netzwerk** | ARP-Tabelle mit Hersteller-Info + Suche |

---

## 🧰 Stack

- **Backend**: Python 3.12 · FastAPI · APScheduler · aiosqlite
- **Frontend**: Vanilla HTML/JS · Chart.js · Dark Theme · Mobile-optimiert
- **Datenbank**: SQLite (lokal, kein externer Dienst nötig)
- **Deployment**: systemd Service · GitHub-Sync via `deploy.sh`

---

## ⚡ Schnellstart

### Voraussetzungen
- Ubuntu Server 22.04+
- Python 3.12+
- OPNsense Router mit API-Zugang

### 1. OPNsense API-Key erstellen

In OPNsense: **System → Access → Users → root → API Keys → „+"**  
Key + Secret aus der heruntergeladenen Datei notieren.

### 2. NetFlow aktivieren (für Per-Client-Statistiken)

In OPNsense: **Reporting → NetFlow**
- Listening interfaces: **LAN**
- WAN interfaces: **STARLINK, WAN**
- **Capture local**: ✅ aktivieren
- Version: **v9**
- → **Apply**

### 3. Installation auf Ubuntu Server

```bash
# Repo clonen
cd /home/alex
git clone https://github.com/schwabe93/HomelabDashboard.git homelabdashboard
cd homelabdashboard

# Python venv + Dependencies
sudo apt install python3.12-venv -y
python3 -m venv venv
./venv/bin/pip install -r requirements.txt

# Datenordner + Konfiguration
mkdir -p data
cp .env.example .env
nano .env
```

### 4. `.env` befüllen

```env
OPNSENSE_HOST=192.168.188.160
OPNSENSE_API_KEY=dein_api_key
OPNSENSE_API_SECRET=dein_api_secret
DATABASE_PATH=data/dashboard.db
```

### 5. Systemd Service

```bash
sudo cp systemd/homelabdashboard.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now homelabdashboard
sudo systemctl status homelabdashboard
```

Dashboard läuft auf: **`http://UBUNTU-SERVER-IP:8080`**

---

## 🔄 Updates deployen

```bash
cd /home/alex/homelabdashboard
bash deploy.sh
```

Das Script führt automatisch aus: `git pull` → `pip install` → `systemctl restart`

### Automatisches Deployment via GitHub Actions

Secrets im GitHub Repo hinterlegen: `SERVER_HOST`, `SERVER_USER`, `SSH_PRIVATE_KEY`

```yaml
# .github/workflows/deploy.yml
name: Deploy
on:
  push:
    branches: [main]
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.SERVER_HOST }}
          username: ${{ secrets.SERVER_USER }}
          key: ${{ secrets.SSH_PRIVATE_KEY }}
          script: bash /home/alex/homelabdashboard/deploy.sh
```

---

## 📁 Projektstruktur

```
homelabdashboard/
├── backend/
│   ├── main.py                    # FastAPI App + Lifespan
│   ├── config.py                  # Einstellungen aus .env
│   ├── database.py                # SQLite Schema + Cleanup
│   ├── scheduler.py               # APScheduler Jobs
│   ├── collectors/
│   │   ├── opnsense_client.py     # HTTP-Client (API Key Auth, HTTPS)
│   │   ├── system_stats.py        # CPU, RAM, Load, Uptime
│   │   ├── interface_traffic.py   # Interface-Raten (Delta-Berechnung)
│   │   ├── traffic_daily.py       # Tägliche Traffic-Aggregation
│   │   ├── firewall_states.py     # Aktive Verbindungen
│   │   ├── firewall_log.py        # Geblockte IPs aus Firewall-Log
│   │   ├── arp_hosts.py           # ARP-Tabelle → IP/MAC/Hersteller
│   │   └── netflow_clients.py     # Per-Client Bandwidth via Insight
│   └── routers/
│       ├── system.py              # GET /api/system[/history]
│       ├── interfaces.py          # GET /api/interfaces[/history]
│       ├── clients.py             # GET /api/clients[/history]
│       ├── firewall.py            # GET /api/firewall/states|blocked
│       ├── hosts.py               # GET /api/hosts
│       ├── gateways.py            # GET /api/gateways
│       ├── dns.py                 # GET /api/dns/stats|top
│       ├── wan.py                 # GET /api/wan, /api/interfaces/errors
│       └── traffic.py             # GET /api/traffic/summary|totals
├── frontend/
│   ├── index.html                 # Single-Page Dashboard
│   ├── css/dashboard.css          # Dark Theme, Mobile-first
│   └── js/
│       ├── app.js                 # Poll-Loop (30s) + Widget-Updates
│       ├── charts.js              # Chart.js Instanzen
│       └── utils.js               # formatBytes, formatBits, etc.
├── systemd/
│   └── homelabdashboard.service
├── .env.example
├── deploy.sh
└── requirements.txt
```

---

## 🗄️ Datenbank

| Tabelle | Inhalt | Aufbewahrung |
|---------|--------|-------------|
| `interface_traffic` | Interface-Raten alle 30s | 7 Tage |
| `traffic_daily` | Tägliche Traffic-Totals pro Interface | 2 Jahre |
| `client_bandwidth` | Per-Client NetFlow-Daten | 24 Stunden |
| `system_snapshots` | CPU/RAM/States alle 60s | 7 Tage |
| `firewall_blocked` | Geblockte Verbindungen | 48 Stunden |
| `arp_cache` | IP → MAC → Hersteller Mapping | Rolling |

---

## 🔧 Collector-Intervalle

| Collector | Intervall | OPNsense API-Endpunkt |
|-----------|-----------|----------------------|
| System Stats | 60s | `diagnostics/activity/getActivity` |
| Interface Traffic | 30s | `diagnostics/traffic/interface` |
| Firewall States | 60s | `diagnostics/firewall/queryStates` |
| Firewall Log | 60s | `diagnostics/firewall/log` |
| ARP Hosts | 120s | `diagnostics/interface/getArp` |
| NetFlow Clients | 300s | `diagnostics/networkinsight/Top` |
| Traffic Daily | 30min | Aggregation aus `interface_traffic` |

---

## 📱 Mobile

Vollständig für Smartphones optimiert:
- Header scrollt horizontal
- Cards stapeln sich in einer Spalte
- Tabellen mit horizontalem Scroll
- Charts mit angepasster Höhe
