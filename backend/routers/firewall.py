from fastapi import APIRouter
import aiosqlite
from collectors import firewall_states
from config import DATABASE_PATH

router = APIRouter()


@router.get("/firewall/states")
async def get_states():
    return firewall_states.get_latest()


@router.get("/firewall/blocked")
async def get_blocked(hours: int = 1):
    cutoff = f"strftime('%s','now') - {hours * 3600}"
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(f"""
            SELECT src_ip, COUNT(*) AS hits,
                   GROUP_CONCAT(DISTINCT protocol) AS protocols,
                   GROUP_CONCAT(DISTINCT dst_port) AS dst_ports
            FROM firewall_blocked
            WHERE timestamp > {cutoff}
            GROUP BY src_ip
            ORDER BY hits DESC
            LIMIT 25
        """) as cur:
            rows = await cur.fetchall()

    return [
        {
            "ip": r["src_ip"],
            "hits": r["hits"],
            "protocols": r["protocols"] or "",
            "dst_ports": r["dst_ports"] or "",
        }
        for r in rows
    ]
