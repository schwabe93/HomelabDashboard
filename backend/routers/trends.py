"""
Langzeit-Trend-Charts und monatlicher Traffic-Bericht.

Endpoints:
  GET /api/trends/system?period=7d|30d|1yr   – CPU/RAM/Load Verlauf (aggregiert)
  GET /api/trends/traffic?period=7d|30d|1yr   – Traffic pro Interface (aus traffic_daily)
  GET /api/trends/dns?period=7d|30d|1yr       – DNS Cache-Hit-Rate Verlauf (falls verfügbar)
  GET /api/trends/report?month=YYYY-MM        – Monatlicher Traffic-Bericht
"""
from __future__ import annotations

import aiosqlite
from fastapi import APIRouter, HTTPException

from config import DATABASE_PATH

router = APIRouter()

# WAN-seitige Interfaces (wie in traffic.py)
WAN_IFACES = {"pppoe0", "vtnet2"}

# Perioden-Definition -> [SQL-Datumsformat für Bucketing, Anzeige-Bucket-Spanne]
_PERIOD_DAYS = {"7d": 7, "30d": 30, "1yr": 365}
_BUCKET_FMT = {"7d": "%Y-%m-%d %H:00", "30d": "%Y-%m-%d", "1yr": "%Y-%m"}


def _period_days(period: str) -> int:
    if period not in _PERIOD_DAYS:
        raise HTTPException(status_code=400, detail=f"invalid period: {period}")
    return _PERIOD_DAYS[period]


def _bucket_fmt(period: str) -> str:
    return _BUCKET_FMT[period]


# ── System Health Trends ───────────────────────────────────────
@router.get("/trends/system")
async def trends_system(period: str = "7d"):
    """Aggregierte CPU/RAM/Load-Werte aus system_snapshots im Zeitverlauf."""
    days = _period_days(period)
    bucket = _bucket_fmt(period)
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            f"""
            SELECT strftime('{bucket}', timestamp, 'unixepoch') AS bucket,
                   MIN(cpu_pct)    AS cpu_min,
                   AVG(cpu_pct)    AS cpu_avg,
                   MAX(cpu_pct)    AS cpu_max,
                   MIN(CASE WHEN mem_total_mb>0 THEN mem_used_mb*100.0/mem_total_mb ELSE 0 END) AS mem_min,
                   AVG(CASE WHEN mem_total_mb>0 THEN mem_used_mb*100.0/mem_total_mb ELSE 0 END) AS mem_avg,
                   MAX(CASE WHEN mem_total_mb>0 THEN mem_used_mb*100.0/mem_total_mb ELSE 0 END) AS mem_max,
                   MIN(load_avg_1) AS load_min,
                   AVG(load_avg_1) AS load_avg,
                   MAX(load_avg_1) AS load_max
            FROM system_snapshots
            WHERE timestamp >= strftime('%s','now') - ? * 86400
            GROUP BY bucket
            ORDER BY bucket ASC
            """,
            (days,),
        ) as cur:
            rows = await cur.fetchall()

    points = [
        {
            "ts": r["bucket"],
            "cpu_min": round(r["cpu_min"] or 0, 1),
            "cpu_avg": round(r["cpu_avg"] or 0, 1),
            "cpu_max": round(r["cpu_max"] or 0, 1),
            "mem_min": round(r["mem_min"] or 0, 1),
            "mem_avg": round(r["mem_avg"] or 0, 1),
            "mem_max": round(r["mem_max"] or 0, 1),
            "load_min": round(r["load_min"] or 0, 2),
            "load_avg": round(r["load_avg"] or 0, 2),
            "load_max": round(r["load_max"] or 0, 2),
        }
        for r in rows
    ]
    # Globale Min/AVG/Max über den gesamten Zeitraum
    summary = _global_summary(points)
    return {"period": period, "points": points, "summary": summary}


def _global_summary(points: list[dict]) -> dict:
    if not points:
        return {}
    metrics = ["cpu_avg", "mem_avg", "load_avg"]
    out = {}
    for m in metrics:
        vals = [p[m] for p in points if p[m] is not None]
        if not vals:
            continue
        out[m.replace("_avg", "_min")] = round(min(vals), 2)
        out[m] = round(sum(vals) / len(vals), 2)
        out[m.replace("_avg", "_max")] = round(max(vals), 2)
    return out


# ── Traffic Trends ─────────────────────────────────────────────
@router.get("/trends/traffic")
async def trends_traffic(period: str = "7d"):
    """Aggregierter Traffic pro Interface aus traffic_daily."""
    days = _period_days(period)
    bucket = _bucket_fmt(period)
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            f"""
            SELECT strftime('{bucket}', date) AS bucket,
                   interface, iface_name,
                   MIN(rx_bytes) AS rx_min,
                   AVG(rx_bytes) AS rx_avg,
                   MAX(rx_bytes) AS rx_max,
                   SUM(rx_bytes) AS rx_total,
                   MIN(tx_bytes) AS tx_min,
                   AVG(tx_bytes) AS tx_avg,
                   MAX(tx_bytes) AS tx_max,
                   SUM(tx_bytes) AS tx_total
            FROM traffic_daily
            WHERE date >= date('now', ?)
            GROUP BY bucket, interface
            ORDER BY bucket ASC, interface ASC
            """,
            (f"-{days} days",),
        ) as cur:
            rows = await cur.fetchall()

    # Gruppieren nach Interface
    ifaces: dict[str, dict] = {}
    buckets: list[str] = []
    for r in rows:
        if r["bucket"] not in buckets:
            buckets.append(r["bucket"])
        key = r["interface"]
        if key not in ifaces:
            ifaces[key] = {"interface": key, "iface_name": r["iface_name"], "rx": {}, "tx": {}}
        ifaces[key]["rx"][r["bucket"]] = {
            "min": r["rx_min"] or 0, "avg": int(r["rx_avg"] or 0),
            "max": r["rx_max"] or 0, "total": r["rx_total"] or 0,
        }
        ifaces[key]["tx"][r["bucket"]] = {
            "min": r["tx_min"] or 0, "avg": int(r["tx_avg"] or 0),
            "max": r["tx_max"] or 0, "total": r["tx_total"] or 0,
        }

    summary = []
    for iface, info in ifaces.items():
        rx_totals = [v["total"] for v in info["rx"].values()]
        tx_totals = [v["total"] for v in info["tx"].values()]
        summary.append({
            "interface": iface,
            "iface_name": info["iface_name"],
            "rx_total": sum(rx_totals),
            "tx_total": sum(tx_totals),
            "rx_avg": int(sum(rx_totals) / max(len(rx_totals), 1)),
            "tx_avg": int(sum(tx_totals) / max(len(tx_totals), 1)),
        })
    summary.sort(key=lambda x: x["rx_total"], reverse=True)

    return {"period": period, "buckets": buckets, "interfaces": list(ifaces.values()), "summary": summary}


# ── DNS Cache-Hit-Rate Trends ──────────────────────────────────
@router.get("/trends/dns")
async def trends_dns(period: str = "7d"):
    """
    DNS Cache-Hit-Rate über Zeit.
    Aktuell gibt es keine persistente DNS-Historie in SQLite -> leere Antwort.
    Falls künftig eine dns_snapshots-Tabelle angelegt wird, kann hier ausgewertet werden.
    """
    days = _period_days(period)
    # Prüfen, ob eine dns_snapshots-Tabelle existiert
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='dns_snapshots'"
        ) as cur:
            exists = await cur.fetchone()

    if not exists:
        return {"period": period, "points": [], "available": False}

    bucket = _bucket_fmt(period)
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            f"""
            SELECT strftime('{bucket}', timestamp, 'unixepoch') AS bucket,
                   AVG(cache_pct) AS cache_avg,
                   AVG(recursion_ms) AS latency_avg
            FROM dns_snapshots
            WHERE timestamp >= strftime('%s','now') - ? * 86400
            GROUP BY bucket
            ORDER BY bucket ASC
            """,
            (days,),
        ) as cur:
            rows = await cur.fetchall()

    points = [
        {
            "ts": r["bucket"],
            "cache_pct": round(r["cache_avg"] or 0, 1),
            "latency_ms": round(r["latency_avg"] or 0, 1),
        }
        for r in rows
    ]
    return {"period": period, "points": points, "available": True}


# ── Monatlicher Traffic-Bericht ───────────────────────────────
@router.get("/trends/report")
async def trends_report(month: str):
    """
    Monatlicher Traffic-Bericht.
    Parameter: month=YYYY-MM (z.B. 2025-06)

    Liefert:
      - Total RX/TX pro Interface für den Monat
      - Top 5 Clients nach Bandbreite (aus client_bandwidth, falls verfügbar)
      - Tägliche Aufschlüsselung
      - Vergleich zum Vormonat (% Veränderung)
    """
    import re
    if not re.match(r"^\d{4}-\d{2}$", month):
        raise HTTPException(status_code=400, detail="month must be YYYY-MM")

    # Vormonat berechnen
    year, mon = month.split("-")
    prev_year = int(year)
    prev_mon = int(mon) - 1
    if prev_mon == 0:
        prev_mon = 12
        prev_year -= 1
    prev_month = f"{prev_year:04d}-{prev_mon:02d}"

    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row

        # Totals pro Interface (aktueller Monat)
        async with db.execute(
            """
            SELECT interface, iface_name,
                   SUM(rx_bytes) AS rx_total,
                   SUM(tx_bytes) AS tx_total
            FROM traffic_daily
            WHERE strftime('%Y-%m', date) = ?
            GROUP BY interface
            ORDER BY rx_total DESC
            """,
            (month,),
        ) as cur:
            rows = await cur.fetchall()
        interface_totals = [dict(r) for r in rows]

        # Totals pro Interface (Vormonat) für Vergleich
        async with db.execute(
            """
            SELECT interface,
                   SUM(rx_bytes) AS rx_total,
                   SUM(tx_bytes) AS tx_total
            FROM traffic_daily
            WHERE strftime('%Y-%m', date) = ?
            GROUP BY interface
            """,
            (prev_month,),
        ) as cur:
            prev_rows = {r["interface"]: dict(r) for r in await cur.fetchall()}

        # Tägliche Aufschlüsselung
        async with db.execute(
            """
            SELECT date, interface, iface_name,
                   rx_bytes, tx_bytes
            FROM traffic_daily
            WHERE strftime('%Y-%m', date) = ?
            ORDER BY date ASC, interface ASC
            """,
            (month,),
        ) as cur:
            daily_rows = await cur.fetchall()
        daily = [dict(r) for r in daily_rows]

        # Top 5 Clients nach Bandbreite (client_bandwidth hat nur 24h)
        # Daher nur sinnvoll, wenn der Monat der aktuelle Monat ist.
        top_clients: list[dict] = []
        async with db.execute(
            """
            SELECT cb.ip_address,
                   COALESCE(a.hostname, a.manufacturer, cb.ip_address) AS display,
                   a.mac,
                   SUM(cb.rx_bytes) AS rx_total,
                   SUM(cb.tx_bytes) AS tx_total
            FROM client_bandwidth cb
            LEFT JOIN arp_cache a ON cb.ip_address = a.ip_address
            WHERE cb.timestamp >= strftime('%s', ? || '-01')
              AND cb.timestamp <  strftime('%s', ? || '-01', '+1 month')
            GROUP BY cb.ip_address
            ORDER BY (rx_total + tx_total) DESC
            LIMIT 5
            """,
            (month, month),
        ) as cur:
            top_clients = [dict(r) for r in await cur.fetchall()]

    # Vergleich zum Vormonat
    comparison = []
    for it in interface_totals:
        iface = it["interface"]
        prev = prev_rows.get(iface, {})
        prev_rx = prev.get("rx_total") or 0
        prev_tx = prev.get("tx_total") or 0
        rx_change = _pct_change(it["rx_total"] or 0, prev_rx)
        tx_change = _pct_change(it["tx_total"] or 0, prev_tx)
        comparison.append({
            "interface": iface,
            "iface_name": it["iface_name"],
            "rx_total": it["rx_total"] or 0,
            "tx_total": it["tx_total"] or 0,
            "prev_rx_total": prev_rx,
            "prev_tx_total": prev_tx,
            "rx_change_pct": rx_change,
            "tx_change_pct": tx_change,
        })

    # Monatssumme
    month_rx = sum((it["rx_total"] or 0) for it in interface_totals)
    month_tx = sum((it["tx_total"] or 0) for it in interface_totals)
    prev_month_rx = sum((v.get("rx_total") or 0) for v in prev_rows.values())
    prev_month_tx = sum((v.get("tx_total") or 0) for v in prev_rows.values())

    return {
        "month": month,
        "previous_month": prev_month,
        "interface_totals": interface_totals,
        "comparison": comparison,
        "daily": daily,
        "top_clients": top_clients,
        "month_rx_total": month_rx,
        "month_tx_total": month_tx,
        "prev_month_rx_total": prev_month_rx,
        "prev_month_tx_total": prev_month_tx,
        "rx_change_pct": _pct_change(month_rx, prev_month_rx),
        "tx_change_pct": _pct_change(month_tx, prev_month_tx),
    }


def _pct_change(current: int, previous: int) -> float | None:
    if previous == 0:
        return None if current == 0 else None  # kein Vergleich möglich
    return round((current - previous) / previous * 100, 1)