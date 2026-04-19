from fastapi import APIRouter
import aiosqlite
from config import DATABASE_PATH

router = APIRouter()

# WAN-side interfaces we want to highlight
WAN_IFACES = {"pppoe0", "vtnet2"}  # WAN PPPoE + STARLINK


@router.get("/traffic/summary")
async def get_traffic_summary(period: str = "day"):
    """
    Returns aggregated download/upload totals per interface.
    period: day | week | month | year
    """
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row

        if period == "day":
            # Today's total from traffic_daily (already accumulated)
            async with db.execute("""
                SELECT interface, iface_name,
                       COALESCE(rx_bytes, 0) AS rx_bytes,
                       COALESCE(tx_bytes, 0) AS tx_bytes,
                       date AS label
                FROM traffic_daily
                WHERE date = date('now')
                ORDER BY rx_bytes DESC
            """) as cur:
                rows = await cur.fetchall()
            return {"period": period, "rows": [dict(r) for r in rows]}

        elif period == "week":
            async with db.execute("""
                SELECT date AS label, interface, iface_name,
                       SUM(rx_bytes) AS rx_bytes,
                       SUM(tx_bytes) AS tx_bytes
                FROM traffic_daily
                WHERE date >= date('now', '-6 days')
                GROUP BY date, interface
                ORDER BY date ASC
            """) as cur:
                rows = await cur.fetchall()
            return {"period": period, "rows": [dict(r) for r in rows]}

        elif period == "month":
            async with db.execute("""
                SELECT date AS label, interface, iface_name,
                       SUM(rx_bytes) AS rx_bytes,
                       SUM(tx_bytes) AS tx_bytes
                FROM traffic_daily
                WHERE date >= date('now', '-29 days')
                GROUP BY date, interface
                ORDER BY date ASC
            """) as cur:
                rows = await cur.fetchall()
            return {"period": period, "rows": [dict(r) for r in rows]}

        elif period == "year":
            # Monthly buckets
            async with db.execute("""
                SELECT strftime('%Y-%m', date) AS label,
                       interface, iface_name,
                       SUM(rx_bytes) AS rx_bytes,
                       SUM(tx_bytes) AS tx_bytes
                FROM traffic_daily
                WHERE date >= date('now', '-364 days')
                GROUP BY strftime('%Y-%m', date), interface
                ORDER BY label ASC
            """) as cur:
                rows = await cur.fetchall()
            return {"period": period, "rows": [dict(r) for r in rows]}

    return {"period": period, "rows": []}


@router.get("/traffic/totals")
async def get_traffic_totals():
    """Quick totals: today, this week, this month for header/summary display."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row

        async with db.execute("""
            SELECT
                SUM(CASE WHEN date = date('now')                    THEN rx_bytes ELSE 0 END) AS rx_today,
                SUM(CASE WHEN date = date('now')                    THEN tx_bytes ELSE 0 END) AS tx_today,
                SUM(CASE WHEN date >= date('now','-6 days')         THEN rx_bytes ELSE 0 END) AS rx_week,
                SUM(CASE WHEN date >= date('now','-6 days')         THEN tx_bytes ELSE 0 END) AS tx_week,
                SUM(CASE WHEN date >= date('now','-29 days')        THEN rx_bytes ELSE 0 END) AS rx_month,
                SUM(CASE WHEN date >= date('now','-29 days')        THEN tx_bytes ELSE 0 END) AS tx_month
            FROM traffic_daily
            WHERE interface IN ('pppoe0','vtnet2')
        """) as cur:
            row = await cur.fetchone()

    if not row:
        return {}
    return {
        "today":  {"rx": row["rx_today"] or 0, "tx": row["tx_today"] or 0},
        "week":   {"rx": row["rx_week"]  or 0, "tx": row["tx_week"]  or 0},
        "month":  {"rx": row["rx_month"] or 0, "tx": row["tx_month"] or 0},
    }
