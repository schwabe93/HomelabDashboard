from fastapi import APIRouter
import aiosqlite
from collectors import netflow_clients
from config import DATABASE_PATH

router = APIRouter()


@router.get("/clients")
async def get_clients():
    enabled = netflow_clients.is_enabled()
    if not enabled:
        return {"netflow_enabled": False, "clients": []}

    cutoff = "strftime('%s','now') - 300"
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row

        async with db.execute(f"""
            SELECT cb.ip_address,
                   SUM(cb.rx_bytes) AS rx_bytes,
                   SUM(cb.tx_bytes) AS tx_bytes,
                   a.mac,
                   a.manufacturer,
                   a.hostname
            FROM client_bandwidth cb
            LEFT JOIN arp_cache a ON cb.ip_address = a.ip_address
            WHERE cb.timestamp > {cutoff}
            GROUP BY cb.ip_address
            ORDER BY rx_bytes DESC
        """) as cur:
            rows = await cur.fetchall()

        async with db.execute(f"""
            SELECT ip_address,
                   SUM(rx_bytes) AS rx_today,
                   SUM(tx_bytes) AS tx_today
            FROM client_bandwidth
            WHERE timestamp > strftime('%s','now') - 86400
            GROUP BY ip_address
        """) as cur:
            today_rows = {r["ip_address"]: r for r in await cur.fetchall()}

    clients = []
    for r in rows:
        ip = r["ip_address"]
        display = r["hostname"] or r["manufacturer"] or ip
        today = today_rows.get(ip)
        clients.append({
            "ip": ip,
            "display": display,
            "mac": r["mac"] or "",
            "manufacturer": r["manufacturer"] or "",
            "rx_5min": r["rx_bytes"],
            "tx_5min": r["tx_bytes"],
            "rx_today": today["rx_today"] if today else 0,
            "tx_today": today["tx_today"] if today else 0,
        })

    return {"netflow_enabled": True, "clients": clients}


@router.get("/clients/history")
async def get_client_history(ip: str, hours: int = 24):
    cutoff = f"strftime('%s','now') - {hours * 3600}"
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            f"SELECT timestamp, rx_bytes, tx_bytes FROM client_bandwidth "
            f"WHERE ip_address=? AND timestamp > {cutoff} ORDER BY timestamp ASC",
            (ip,),
        ) as cur:
            rows = await cur.fetchall()

    return [{"ts": r["timestamp"], "rx": r["rx_bytes"], "tx": r["tx_bytes"]} for r in rows]
