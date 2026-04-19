import time
import aiosqlite
from collectors.opnsense_client import api_get
from config import DATABASE_PATH

_prev: dict[str, dict] = {}


async def collect():
    try:
        data = await api_get("diagnostics/traffic/interface")
        ifaces = data.get("interfaces", {})
        now = int(time.time())
        rows = []

        for key, stats in ifaces.items():
            device = stats.get("device", key)
            name = stats.get("name", key.upper())
            rx = int(stats.get("bytes received", 0))
            tx = int(stats.get("bytes transmitted", 0))

            rx_rate = tx_rate = 0
            if device in _prev:
                prev = _prev[device]
                dt = now - prev["ts"]
                if dt > 0:
                    rx_delta = rx - prev["rx"]
                    tx_delta = tx - prev["tx"]
                    rx_rate = max(0, rx_delta * 8 // dt)
                    tx_rate = max(0, tx_delta * 8 // dt)

            _prev[device] = {"rx": rx, "tx": tx, "ts": now}
            rows.append((now, device, name, rx, tx, rx_rate, tx_rate))

        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.executemany(
                "INSERT INTO interface_traffic (timestamp,interface,iface_name,rx_bytes,tx_bytes,rx_rate_bps,tx_rate_bps) VALUES (?,?,?,?,?,?,?)",
                rows,
            )
            await db.commit()
    except Exception as e:
        print(f"[interface_traffic] error: {e}")
