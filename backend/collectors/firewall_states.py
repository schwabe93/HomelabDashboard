import aiosqlite
from collectors.opnsense_client import api_post
from config import DATABASE_PATH

_latest_total = 0
_latest_top: list = []


async def collect():
    global _latest_total, _latest_top
    try:
        data = await api_post("diagnostics/firewall/queryStates", {"rowCount": 1000})
        _latest_total = data.get("total", 0)

        src_counts: dict[str, int] = {}
        for row in data.get("rows", []):
            src = row.get("src_addr", "")
            if src:
                src_counts[src] = src_counts.get(src, 0) + 1

        _latest_top = sorted(src_counts.items(), key=lambda x: x[1], reverse=True)[:15]

        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute(
                "UPDATE system_snapshots SET active_states=? WHERE id=(SELECT MAX(id) FROM system_snapshots)",
                (_latest_total,),
            )
            await db.commit()
    except Exception as e:
        print(f"[firewall_states] error: {e}")


def get_latest() -> dict:
    return {"total": _latest_total, "top_sources": [{"ip": ip, "count": cnt} for ip, cnt in _latest_top]}
