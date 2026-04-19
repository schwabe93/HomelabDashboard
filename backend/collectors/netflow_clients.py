import time
import aiosqlite
from collectors.opnsense_client import api_get, api_post
from config import DATABASE_PATH

_netflow_enabled: bool | None = None


async def collect():
    global _netflow_enabled
    try:
        if _netflow_enabled is None:
            status = await api_get("diagnostics/netflow/isEnabled")
            _netflow_enabled = bool(status.get("netflow", 0))

        if not _netflow_enabled:
            return

        data = await api_post("diagnostics/networkinsight/Top", {
            "interface": "vtnet0",
            "resolver": "FlowSourceAddrTotals",
            "start_time": "now-300",
            "end_time": "now",
        })

        clients = data if isinstance(data, list) else data.get("rows", [])
        if not clients:
            return

        now = int(time.time())
        rows = [
            (now, c.get("address", ""), int(c.get("in_bytes", 0)), int(c.get("out_bytes", 0)))
            for c in clients
            if c.get("address")
        ]

        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.executemany(
                "INSERT INTO client_bandwidth (timestamp,ip_address,rx_bytes,tx_bytes) VALUES (?,?,?,?)",
                rows,
            )
            await db.commit()
    except Exception as e:
        print(f"[netflow_clients] error: {e}")


def is_enabled() -> bool:
    return _netflow_enabled is True
