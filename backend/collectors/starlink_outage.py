"""
Starlink Outage Tracker – Collector.

Pollt den Starlink-Status alle 60s (über /api/starlink/status intern bzw.
direkt über die Starlink-Router-Funktionen) und protokolliert Statuswechsel
(online <-> offline) in der SQLite-Tabelle `starlink_outages`.

Schema der Tabelle:
  id, timestamp, event (online/offline), duration_s, latency_ms

Der Collector merkt sich den letzten Zustand. Bei einem Wechsel wird
ein Eintrag geschrieben: timestamp = Zeitpunkt des Wechsels,
event = neuer Zustand, duration_s = Dauer des vorherigen Zustands,
latency_ms = Latenz zum Zeitpunkt des Wechsels (falls verfügbar).
"""
from __future__ import annotations

import asyncio
import time
import aiosqlite

from config import DATABASE_PATH, STARLINK_HOST, STARLINK_GRPC_PORT

# Tabelle beim ersten Start anlegen
_SCHEMA = """
CREATE TABLE IF NOT EXISTS starlink_outages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   INTEGER NOT NULL,
    event       TEXT NOT NULL,        -- 'online' | 'offline'
    duration_s  REAL DEFAULT 0,       -- Dauer des vorherigen Zustands
    latency_ms  REAL                  -- Latenz zum Zeitpunkt des Wechsels
);
CREATE INDEX IF NOT EXISTS idx_starlink_outages_ts ON starlink_outages(timestamp);
"""

_state: dict = {
    "last_event": None,   # 'online' | 'offline' | None
    "since": None,         # timestamp des letzten Wechsels
}


async def _ensure_schema(db: aiosqlite.Connection):
    for stmt in _SCHEMA.strip().split(";"):
        s = stmt.strip()
        if s:
            await db.execute(s)
    await db.commit()


async def _init_state():
    """Letzten Zustand aus der DB laden, falls vorhanden."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await _ensure_schema(db)
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT event, timestamp FROM starlink_outages ORDER BY id DESC LIMIT 1"
        ) as cur:
            row = await cur.fetchone()
        if row:
            _state["last_event"] = row["event"]
            _state["since"] = row["timestamp"]
        else:
            _state["last_event"] = None
            _state["since"] = None


_initialized = False


async def _determine_status() -> tuple[str, float | None]:
    """
    Bestimmt den aktuellen Starlink-Status.
    Versucht zuerst gRPC, fällt auf Ping zurück.
    Gibt (status, latency_ms) zurück.
    """
    from routers import starlink as starlink_router

    host = STARLINK_HOST
    port = STARLINK_GRPC_PORT

    try:
        reachable, grpc_open = await asyncio.gather(
            starlink_router.ping_host(host),
            starlink_router.tcp_check(host, port),
        )
    except Exception:
        return "offline", None

    latency_ms: float | None = None
    online = reachable or grpc_open

    # Falls gRPC offen ist, versuchen wir die Latenz zu ermitteln
    if grpc_open:
        try:
            result = await starlink_router.grpcurl_ping(host, port)
            if result.get("latency_ms") is not None:
                latency_ms = float(result["latency_ms"])
        except Exception:
            pass

    return ("online" if online else "offline"), latency_ms


async def collect():
    """Wird vom Scheduler alle 60s aufgerufen."""
    global _initialized
    if not _initialized:
        await _init_state()
        _initialized = True

    try:
        status, latency_ms = await _determine_status()
    except Exception as e:
        print(f"[starlink_outage] status check failed: {e}")
        return

    now = int(time.time())
    last = _state["last_event"]

    if last is None:
        # Erster Lauf: initialen Zustand ohne Wechsel-Eintrag setzen
        _state["last_event"] = status
        _state["since"] = now
        # Initialen Zustand trotzdem protokollieren, damit die Timeline Daten hat
        await _log_event(now, status, 0.0, latency_ms)
        return

    if status == last:
        # Kein Wechsel -> nichts tun
        return

    # Statuswechsel -> Eintrag loggen
    duration_s = 0.0
    if _state["since"] is not None:
        duration_s = round(now - _state["since"], 1)

    await _log_event(now, status, duration_s, latency_ms)
    _state["last_event"] = status
    _state["since"] = now
    print(f"[starlink_outage] state change: {last} -> {status} (prev duration {duration_s}s)")


async def _log_event(ts: int, event: str, duration_s: float, latency_ms: float | None):
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await _ensure_schema(db)
            await db.execute(
                "INSERT INTO starlink_outages (timestamp, event, duration_s, latency_ms) "
                "VALUES (?, ?, ?, ?)",
                (ts, event, duration_s, latency_ms),
            )
            await db.commit()
    except Exception as e:
        print(f"[starlink_outage] log error: {e}")