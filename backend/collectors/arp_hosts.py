import time
import aiosqlite
from collectors.opnsense_client import api_get
from config import DATABASE_PATH


async def collect():
    try:
        data = await api_get("diagnostics/interface/getArp")
        entries = data if isinstance(data, list) else data.get("data", [])
        now = int(time.time())

        rows = [
            (
                e["ip"],
                e.get("mac", ""),
                e.get("manufacturer", ""),
                e.get("hostname", ""),
                e.get("intf", ""),
                now,
            )
            for e in entries
            if e.get("ip")
        ]

        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.executemany(
                "INSERT OR REPLACE INTO arp_cache (ip_address,mac,manufacturer,hostname,interface,updated_at) VALUES (?,?,?,?,?,?)",
                rows,
            )
            await db.commit()
    except Exception as e:
        print(f"[arp_hosts] error: {e}")
