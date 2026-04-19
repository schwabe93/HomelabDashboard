from fastapi import APIRouter
import aiosqlite
from config import DATABASE_PATH

router = APIRouter()


@router.get("/interfaces")
async def get_interfaces():
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT i1.*
            FROM interface_traffic i1
            INNER JOIN (
                SELECT interface, MAX(timestamp) AS max_ts
                FROM interface_traffic
                GROUP BY interface
            ) i2 ON i1.interface = i2.interface AND i1.timestamp = i2.max_ts
            ORDER BY i1.iface_name
        """) as cur:
            rows = await cur.fetchall()

    return [
        {
            "interface": r["interface"],
            "name": r["iface_name"],
            "rx_rate_bps": r["rx_rate_bps"],
            "tx_rate_bps": r["tx_rate_bps"],
            "rx_bytes_total": r["rx_bytes"],
            "tx_bytes_total": r["tx_bytes"],
            "timestamp": r["timestamp"],
        }
        for r in rows
    ]


@router.get("/interfaces/history")
async def get_interface_history(iface: str, hours: int = 1):
    cutoff = f"strftime('%s','now') - {hours * 3600}"
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            f"SELECT timestamp, rx_rate_bps, tx_rate_bps FROM interface_traffic "
            f"WHERE interface=? AND timestamp > {cutoff} ORDER BY timestamp ASC",
            (iface,),
        ) as cur:
            rows = await cur.fetchall()

    return [{"ts": r["timestamp"], "rx": r["rx_rate_bps"], "tx": r["tx_rate_bps"]} for r in rows]
