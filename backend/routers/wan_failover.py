"""Multi-WAN failover visualization router — tracks active/standby gateways and failover events."""
import time
from typing import Any

import aiosqlite
from fastapi import APIRouter

from collectors.opnsense_client import api_get
from config import DATABASE_PATH

router = APIRouter()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS wan_failover_events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp    INTEGER NOT NULL,
    from_wan     TEXT NOT NULL DEFAULT '',
    to_wan       TEXT NOT NULL DEFAULT '',
    reason       TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_wanfailover_ts ON wan_failover_events(timestamp);

CREATE TABLE IF NOT EXISTS wan_failover_state (
    id           INTEGER PRIMARY KEY CHECK (id = 1),
    active_wan   TEXT DEFAULT '',
    standby_wan  TEXT DEFAULT '',
    updated_at   INTEGER DEFAULT 0
);
"""


async def _ensure_schema(db: aiosqlite.Connection) -> None:
    for stmt in _SCHEMA.strip().split(";"):
        s = stmt.strip()
        if s:
            await db.execute(s)
    await db.commit()


async def _fetch_gateways() -> list[dict[str, Any]]:
    """Fetch current gateway status (mirrors routers/gateways.py)."""
    try:
        data = await api_get("routes/gateway/status")
        items = data.get("items", []) if isinstance(data, dict) else []
        result = []
        for gw in items:
            status = gw.get("status_translated", "Unknown")
            result.append({
                "name": gw.get("name", ""),
                "address": gw.get("address", ""),
                "monitor": gw.get("monitor", ""),
                "status": status,
                "online": status.lower() == "online",
                "loss": gw.get("loss", "—"),
                "delay": gw.get("delay", "—"),
            })
        return result
    except Exception:
        return []


def _classify_gateways(gateways: list[dict[str, Any]]) -> tuple[str | None, str | None, list[dict[str, Any]]]:
    """Determine active and standby WAN from gateway list.

    Heuristic: 'online' gateways are active candidates; among offline ones, pick as standby.
    If multiple online, the first is treated as primary (active). Gateway names containing
    'starlink' are labelled accordingly for the UI.
    """
    if not gateways:
        return None, None, []

    online = [g for g in gateways if g["online"]]
    offline = [g for g in gateways if not g["online"]]

    # Active = first online gateway; if none online, active is None (or the least-bad offline)
    active = online[0]["name"] if online else (offline[0]["name"] if offline else None)

    # Standby = first gateway that is not active
    standby = None
    for g in gateways:
        if g["name"] != active:
            standby = g["name"]
            break

    return active, standby, gateways


async def _get_stored_state(db: aiosqlite.Connection) -> tuple[str, str]:
    """Return (active_wan, standby_wan) stored in DB, or ('', '')."""
    async with db.execute("SELECT active_wan, standby_wan FROM wan_failover_state WHERE id = 1") as cur:
        row = await cur.fetchone()
    if row:
        return row[0] or "", row[1] or ""
    return "", ""


async def _store_state(db: aiosqlite.Connection, active: str, standby: str) -> None:
    now = int(time.time())
    await db.execute(
        "INSERT INTO wan_failover_state (id, active_wan, standby_wan, updated_at) VALUES (1, ?, ?, ?) "
        "ON CONFLICT(id) DO UPDATE SET active_wan=excluded.active_wan, standby_wan=excluded.standby_wan, updated_at=excluded.updated_at",
        (active, standby, now),
    )
    await db.commit()


async def _log_event(db: aiosqlite.Connection, from_wan: str, to_wan: str, reason: str = "") -> None:
    await db.execute(
        "INSERT INTO wan_failover_events (timestamp, from_wan, to_wan, reason) VALUES (?, ?, ?, ?)",
        (int(time.time()), from_wan, to_wan, reason),
    )
    await db.commit()


@router.get("/wan/failover")
async def get_failover() -> dict[str, Any]:
    """Return current failover state and statistics."""
    gateways = await _fetch_gateways()
    active, standby, gw_list = _classify_gateways(gateways)

    async with aiosqlite.connect(DATABASE_PATH) as db:
        await _ensure_schema(db)

        prev_active, prev_standby = await _get_stored_state(db)

        # Detect a failover: active changed from a non-empty previous value
        last_failover_time = None
        failover_count_24h = 0
        if prev_active and active and prev_active != active:
            await _log_event(db, prev_active, active, reason=f"Aktiver Gateway wechselte von {prev_active} zu {active}")

        if active is not None or standby is not None:
            await _store_state(db, active or "", standby or "")

        # Last failover time
        async with db.execute(
            "SELECT timestamp FROM wan_failover_events ORDER BY timestamp DESC LIMIT 1"
        ) as cur:
            ev_row = await cur.fetchone()
        if ev_row:
            last_failover_time = ev_row[0]

        # Failover count in last 24h
        cutoff_24h = int(time.time()) - 86400
        async with db.execute(
            "SELECT COUNT(*) FROM wan_failover_events WHERE timestamp >= ?", (cutoff_24h,)
        ) as cur:
            count_row = await cur.fetchone()
        failover_count_24h = count_row[0] if count_row else 0

    # Build gateway display info with labels (Starlink / WAN)
    gw_display = []
    for g in gw_list:
        name = g["name"]
        label = "Starlink" if "starlink" in name.lower() else ("WAN" if "wan" in name.lower() else name)
        gw_display.append({
            "name": name,
            "label": label,
            "address": g["address"],
            "status": g["status"],
            "online": g["online"],
            "delay": g["delay"],
            "loss": g["loss"],
            "role": "active" if name == active else ("standby" if name == standby else "other"),
        })

    return {
        "current_active_wan": active,
        "current_standby": standby,
        "gateways": gw_display,
        "last_failover_time": last_failover_time,
        "last_failover_time_str": time.strftime("%d.%m.%Y %H:%M:%S", time.localtime(last_failover_time)) if last_failover_time else "—",
        "failover_count_24h": failover_count_24h,
    }


@router.get("/wan/failover/history")
async def failover_history(limit: int = 100) -> dict[str, Any]:
    """Return historical failover events, and poll/log current state."""
    gateways = await _fetch_gateways()
    active, standby, _ = _classify_gateways(gateways)

    async with aiosqlite.connect(DATABASE_PATH) as db:
        await _ensure_schema(db)

        prev_active, _ = await _get_stored_state(db)
        if prev_active and active and prev_active != active:
            await _log_event(db, prev_active, active, reason=f"Aktiver Gateway wechselte von {prev_active} zu {active}")
        if active is not None or standby is not None:
            await _store_state(db, active or "", standby or "")

        limit = max(1, min(limit, 500))
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT timestamp, from_wan, to_wan, reason FROM wan_failover_events "
            "ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        ) as cur:
            rows = await cur.fetchall()

    events = [
        {
            "timestamp": r["timestamp"],
            "time": time.strftime("%d.%m.%Y %H:%M:%S", time.localtime(r["timestamp"])),
            "from_wan": r["from_wan"],
            "to_wan": r["to_wan"],
            "reason": r["reason"],
        }
        for r in rows
    ]

    return {
        "current_active_wan": active,
        "current_standby": standby,
        "events": events,
        "count": len(events),
    }