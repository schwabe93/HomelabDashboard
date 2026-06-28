"""
Starlink Outage Tracking – API-Router.

Endpoint:
  GET /api/starlink/outages?period=24h|7d  – Liste der Outage-Ereignisse
"""
from __future__ import annotations

import time
from fastapi import APIRouter, HTTPException

import aiosqlite
from config import DATABASE_PATH

router = APIRouter()

_PERIOD_SECS = {"24h": 86400, "7d": 604800}


def _period_secs(period: str) -> int:
    if period not in _PERIOD_SECS:
        raise HTTPException(status_code=400, detail=f"invalid period: {period}")
    return _PERIOD_SECS[period]


@router.get("/starlink/outages")
async def get_starlink_outages(period: str = "7d"):
    """
    Liefert die Outage-Ereignisse sowie eine Uptime-Statistik.

    Antwort:
      events:    [{timestamp, event, duration_s, latency_ms}]
      uptime_pct: Uptime in Prozent im Zeitraum
      total_downtime_s: Gesamtausfallzeit in Sekunden
      outage_count: Anzahl der Offline-Phasen
      longest_outage_s: Längste Einzelausfallzeit
    """
    secs = _period_secs(period)
    cutoff = int(time.time()) - secs

    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT timestamp, event, duration_s, latency_ms
            FROM starlink_outages
            WHERE timestamp >= ?
            ORDER BY timestamp ASC
            """,
            (cutoff,),
        ) as cur:
            rows = await cur.fetchall()

    events = [dict(r) for r in rows]

    # Uptime-Statistik berechnen
    uptime_pct, total_downtime_s, outage_count, longest_outage_s = _compute_stats(events, cutoff)

    return {
        "period": period,
        "events": events,
        "uptime_pct": round(uptime_pct, 2),
        "total_downtime_s": round(total_downtime_s, 1),
        "outage_count": outage_count,
        "longest_outage_s": round(longest_outage_s, 1),
    }


def _compute_stats(events: list[dict], cutoff: int) -> tuple[float, float, int, float]:
    """
    Berechnet Uptime-Prozentsatz, Gesamtausfall, Anzahl Outages und längsten
    Ausfall anhand der Event-Liste.

    Logik:
      - Iteriere über Events. Ein 'offline' Event markiert den Beginn einer
        Ausfallphase. Die Dauer der Ausfallphase ist die duration_s des
        nachfolgenden 'online' Events (sofern vorhanden).
      - Falls der letzte Zustand 'offline' ist und der Zeitraum noch läuft,
        wird die verbleibende Zeit bis jetzt als Ausfall gezählt.
    """
    now = int(time.time())
    total_period = now - cutoff
    if total_period <= 0 or not events:
        return (100.0, 0.0, 0, 0.0)

    total_downtime = 0.0
    outage_count = 0
    longest = 0.0
    offline_since: int | None = None

    for ev in events:
        ts = ev["timestamp"]
        if ev["event"] == "offline":
            outage_count += 1
            offline_since = ts
        elif ev["event"] == "online":
            if offline_since is not None:
                dur = ts - offline_since
                if dur > 0:
                    total_downtime += dur
                    longest = max(longest, dur)
                offline_since = None
            # Falls 'online' ohne vorheriges 'offline': ignoriere (Start)
        # duration_s wird für die Timeline nicht direkt verwendet, da wir
        # anhand der Zeitstempel rechnen – ist aber in events verfügbar.

    # Falls aktuell offline -> Restdauer bis jetzt
    if offline_since is not None:
        dur = now - offline_since
        if dur > 0:
            total_downtime += dur
            longest = max(longest, dur)

    uptime_pct = max(0.0, 100.0 - (total_downtime / total_period * 100.0))
    return (uptime_pct, total_downtime, outage_count, longest)