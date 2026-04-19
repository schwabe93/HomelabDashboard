import time
import aiosqlite
from collectors.opnsense_client import api_post
from config import DATABASE_PATH

_last_seen_ts: str = ""


async def collect():
    global _last_seen_ts
    try:
        data = await api_post("diagnostics/firewall/log", {"rowCount": 200})
        rows_raw = data if isinstance(data, list) else data.get("rows", [])

        blocked = [r for r in rows_raw if r.get("action") == "block"]
        if not blocked:
            return

        now = int(time.time())
        rows = [
            (
                now,
                r.get("src", r.get("__src__", "")),
                r.get("dst", r.get("__dst__", "")),
                str(r.get("dstport", r.get("dst_port", ""))),
                r.get("protoname", r.get("proto", "")),
                r.get("interface", ""),
                r.get("dir", r.get("direction", "")),
            )
            for r in blocked
            if r.get("src", r.get("__src__", ""))
        ]

        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.executemany(
                "INSERT INTO firewall_blocked (timestamp,src_ip,dst_ip,dst_port,protocol,interface,direction) VALUES (?,?,?,?,?,?,?)",
                rows,
            )
            await db.commit()
    except Exception as e:
        print(f"[firewall_log] error: {e}")
