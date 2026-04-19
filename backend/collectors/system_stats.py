import re
import time
import aiosqlite
from collectors.opnsense_client import api_get
from config import DATABASE_PATH


async def collect():
    try:
        activity, resources, disk, info = await _fetch_all()
        row = _parse(activity, resources, disk)
        await _store(row)
    except Exception as e:
        print(f"[system_stats] error: {e}")


async def _fetch_all():
    import asyncio
    return await asyncio.gather(
        api_get("diagnostics/activity/getActivity"),
        api_get("diagnostics/system/systemResources"),
        api_get("diagnostics/system/systemDisk"),
        api_get("diagnostics/system/systemInformation"),
    )


def _parse(activity: dict, resources: dict, disk: dict) -> tuple:
    now = int(time.time())

    headers = activity.get("headers", [])
    cpu_pct = 0.0
    load_1 = load_5 = load_15 = 0.0
    uptime_str = ""

    if len(headers) > 0:
        m = re.search(r"load averages:\s+([\d.]+),\s+([\d.]+),\s+([\d.]+)", headers[0])
        if m:
            load_1, load_5, load_15 = float(m.group(1)), float(m.group(2)), float(m.group(3))
        m = re.search(r"up\s+(\S+)\s+\d+:\d+:\d+", headers[0])
        if m:
            uptime_str = m.group(1)

    if len(headers) > 2:
        m = re.search(r"([\d.]+)%\s+idle", headers[2])
        if m:
            cpu_pct = round(100.0 - float(m.group(1)), 1)

    mem = resources.get("memory", {})
    mem_total_mb = int(int(mem.get("total", 0)) / 1_048_576)
    mem_used_mb = int(int(mem.get("used", 0)) / 1_048_576)

    disk_pct = 0
    devices = disk.get("devices", [])
    if devices:
        disk_pct = devices[0].get("used_pct", 0)

    return (now, cpu_pct, mem_used_mb, mem_total_mb, 0, load_1, load_5, load_15, disk_pct, uptime_str)


async def _store(row: tuple):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "INSERT INTO system_snapshots "
            "(timestamp,cpu_pct,mem_used_mb,mem_total_mb,active_states,load_avg_1,load_avg_5,load_avg_15,disk_pct,uptime_str) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            row,
        )
        await db.commit()
