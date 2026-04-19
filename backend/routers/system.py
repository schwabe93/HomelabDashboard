from fastapi import APIRouter
import aiosqlite
from config import DATABASE_PATH
from collectors.opnsense_client import api_get
from collectors import firewall_states

router = APIRouter()


@router.get("/system")
async def get_system():
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM system_snapshots ORDER BY id DESC LIMIT 1"
        ) as cur:
            row = await cur.fetchone()

    info = await api_get("diagnostics/system/systemInformation")
    states = firewall_states.get_latest()

    return {
        "hostname": info.get("name", "OPNsense"),
        "version": info.get("versions", [""])[0],
        "cpu_pct": row["cpu_pct"] if row else 0,
        "mem_used_mb": row["mem_used_mb"] if row else 0,
        "mem_total_mb": row["mem_total_mb"] if row else 0,
        "load_avg_1": row["load_avg_1"] if row else 0,
        "load_avg_5": row["load_avg_5"] if row else 0,
        "load_avg_15": row["load_avg_15"] if row else 0,
        "disk_pct": row["disk_pct"] if row else 0,
        "uptime_str": row["uptime_str"] if row else "",
        "active_states": states["total"],
        "timestamp": row["timestamp"] if row else 0,
    }


@router.get("/system/history")
async def get_system_history(hours: int = 24):
    cutoff = f"strftime('%s','now') - {hours * 3600}"
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            f"SELECT timestamp, cpu_pct, mem_used_mb, mem_total_mb, active_states "
            f"FROM system_snapshots WHERE timestamp > {cutoff} ORDER BY timestamp ASC"
        ) as cur:
            rows = await cur.fetchall()

    return [
        {
            "ts": r["timestamp"],
            "cpu_pct": r["cpu_pct"],
            "mem_pct": round(r["mem_used_mb"] / r["mem_total_mb"] * 100, 1) if r["mem_total_mb"] else 0,
            "active_states": r["active_states"],
        }
        for r in rows
    ]
