"""
Aggregates daily traffic totals from interface_traffic rates.
Runs every hour and upserts today's accumulated bytes.
Uses SUM(rate_bps * interval / 8) which is robust against OPNsense reboots.
"""
import aiosqlite
from config import DATABASE_PATH

# Approximate polling interval in seconds (matches scheduler interval)
_POLL_INTERVAL = 30


async def collect():
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row
            # Sum rates for today (since midnight UTC)
            async with db.execute("""
                SELECT interface,
                       iface_name,
                       SUM(rx_rate_bps * ? / 8) AS rx_bytes,
                       SUM(tx_rate_bps * ? / 8) AS tx_bytes
                FROM interface_traffic
                WHERE timestamp >= strftime('%s', date('now'))
                  AND timestamp <  strftime('%s', date('now','+1 day'))
                GROUP BY interface
            """, (_POLL_INTERVAL, _POLL_INTERVAL)) as cur:
                rows = await cur.fetchall()

            today = "date('now')"
            for r in rows:
                await db.execute("""
                    INSERT INTO traffic_daily (date, interface, iface_name, rx_bytes, tx_bytes)
                    VALUES (date('now'), ?, ?, ?, ?)
                    ON CONFLICT(date, interface) DO UPDATE SET
                        rx_bytes = excluded.rx_bytes,
                        tx_bytes = excluded.tx_bytes
                """, (r["interface"], r["iface_name"], int(r["rx_bytes"] or 0), int(r["tx_bytes"] or 0)))

            await db.commit()
    except Exception as e:
        print(f"[traffic_daily] error: {e}")
