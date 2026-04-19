import aiosqlite
import os
from config import DATABASE_PATH

_db_path = DATABASE_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS interface_traffic (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   INTEGER NOT NULL,
    interface   TEXT NOT NULL,
    iface_name  TEXT NOT NULL,
    rx_bytes    INTEGER NOT NULL,
    tx_bytes    INTEGER NOT NULL,
    rx_rate_bps INTEGER NOT NULL DEFAULT 0,
    tx_rate_bps INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_itraffic_ts ON interface_traffic(timestamp);
CREATE INDEX IF NOT EXISTS idx_itraffic_if ON interface_traffic(interface, timestamp);

CREATE TABLE IF NOT EXISTS client_bandwidth (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   INTEGER NOT NULL,
    ip_address  TEXT NOT NULL,
    rx_bytes    INTEGER NOT NULL DEFAULT 0,
    tx_bytes    INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_cbw_ts  ON client_bandwidth(timestamp);
CREATE INDEX IF NOT EXISTS idx_cbw_ip  ON client_bandwidth(ip_address, timestamp);

CREATE TABLE IF NOT EXISTS firewall_blocked (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   INTEGER NOT NULL,
    src_ip      TEXT NOT NULL,
    dst_ip      TEXT,
    dst_port    TEXT,
    protocol    TEXT,
    interface   TEXT,
    direction   TEXT
);
CREATE INDEX IF NOT EXISTS idx_fblocked_ts    ON firewall_blocked(timestamp);
CREATE INDEX IF NOT EXISTS idx_fblocked_srcip ON firewall_blocked(src_ip);

CREATE TABLE IF NOT EXISTS system_snapshots (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp     INTEGER NOT NULL,
    cpu_pct       REAL NOT NULL DEFAULT 0,
    mem_used_mb   INTEGER NOT NULL DEFAULT 0,
    mem_total_mb  INTEGER NOT NULL DEFAULT 0,
    active_states INTEGER NOT NULL DEFAULT 0,
    load_avg_1    REAL DEFAULT 0,
    load_avg_5    REAL DEFAULT 0,
    load_avg_15   REAL DEFAULT 0,
    disk_pct      INTEGER DEFAULT 0,
    uptime_str    TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_syssnap_ts ON system_snapshots(timestamp);

CREATE TABLE IF NOT EXISTS arp_cache (
    ip_address   TEXT PRIMARY KEY,
    mac          TEXT,
    manufacturer TEXT,
    hostname     TEXT DEFAULT '',
    interface    TEXT,
    updated_at   INTEGER NOT NULL
);
"""


async def init_db():
    os.makedirs(os.path.dirname(_db_path) if os.path.dirname(_db_path) else ".", exist_ok=True)
    async with aiosqlite.connect(_db_path) as db:
        for stmt in SCHEMA.strip().split(";"):
            s = stmt.strip()
            if s:
                await db.execute(s)
        await db.commit()


async def get_db():
    return await aiosqlite.connect(_db_path)


async def purge_old_data():
    async with aiosqlite.connect(_db_path) as db:
        await db.execute("DELETE FROM interface_traffic WHERE timestamp < strftime('%s','now') - 604800")
        await db.execute("DELETE FROM client_bandwidth   WHERE timestamp < strftime('%s','now') - 86400")
        await db.execute("DELETE FROM firewall_blocked   WHERE timestamp < strftime('%s','now') - 172800")
        await db.execute("DELETE FROM system_snapshots   WHERE timestamp < strftime('%s','now') - 604800")
        await db.commit()
