from fastapi import APIRouter
import aiosqlite
from config import DATABASE_PATH

router = APIRouter()


@router.get("/hosts")
async def get_hosts():
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT ip_address, mac, manufacturer, hostname, interface, updated_at "
            "FROM arp_cache ORDER BY ip_address ASC"
        ) as cur:
            rows = await cur.fetchall()

    return [
        {
            "ip": r["ip_address"],
            "mac": r["mac"],
            "manufacturer": r["manufacturer"],
            "hostname": r["hostname"],
            "interface": r["interface"],
            "updated_at": r["updated_at"],
        }
        for r in rows
    ]
