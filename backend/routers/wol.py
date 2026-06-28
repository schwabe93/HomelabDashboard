"""Wake-on-LAN router — sends magic packets and tracks wake history."""
import re
import socket
import time
from typing import Any

import aiosqlite
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from config import DATABASE_PATH

router = APIRouter()

MAC_RE = re.compile(r"^[0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){5}$")
DEFAULT_BROADCAST = "255.255.255.255"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS wol_history (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp     INTEGER NOT NULL,
    mac           TEXT NOT NULL,
    broadcast_ip  TEXT NOT NULL DEFAULT '',
    hostname      TEXT DEFAULT '',
    ip            TEXT DEFAULT '',
    status        TEXT NOT NULL DEFAULT 'ok',
    message       TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_wol_ts ON wol_history(timestamp);
"""


async def _ensure_schema(db: aiosqlite.Connection) -> None:
    for stmt in _SCHEMA.strip().split(";"):
        s = stmt.strip()
        if s:
            await db.execute(s)
    await db.commit()


def _build_magic_packet(mac: str) -> bytes:
    """Build a WoL magic packet: 6x 0xFF + 16x MAC (no separators)."""
    cleaned = mac.replace(":", "").replace("-", "").replace(".", "")
    if len(cleaned) != 12:
        raise ValueError(f"Ungültige MAC-Adresse: {mac}")
    mac_bytes = bytes.fromhex(cleaned)
    return b"\xff" * 6 + mac_bytes * 16


def _send_packet(mac: str, broadcast_ip: str) -> tuple[bool, str]:
    """Send a magic packet via UDP broadcast. Returns (success, message)."""
    try:
        packet = _build_magic_packet(mac)
    except ValueError as e:
        return False, str(e)

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(2.0)
        sock.sendto(packet, (broadcast_ip or DEFAULT_BROADCAST, 9))
        sock.close()
        return True, "Magic Packet gesendet"
    except OSError as e:
        return False, f"Fehler beim Senden: {e}"


class WoLPayload(BaseModel):
    mac: str
    broadcast_ip: str = DEFAULT_BROADCAST
    hostname: str = ""
    ip: str = ""


@router.post("/wol/send")
async def send_wol(payload: WoLPayload) -> dict[str, Any]:
    """Send a Wake-on-LAN magic packet and log the attempt."""
    mac = payload.mac.strip().lower()
    broadcast = payload.broadcast_ip.strip() or DEFAULT_BROADCAST

    if not MAC_RE.match(mac):
        raise HTTPException(status_code=400, detail=f"Ungültige MAC-Adresse: {payload.mac}")

    success, message = await _send_async(mac, broadcast)
    status = "ok" if success else "error"

    async with aiosqlite.connect(DATABASE_PATH) as db:
        await _ensure_schema(db)
        await db.execute(
            "INSERT INTO wol_history (timestamp, mac, broadcast_ip, hostname, ip, status, message) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (int(time.time()), mac, broadcast, payload.hostname, payload.ip, status, message),
        )
        await db.commit()

    return {
        "ok": success,
        "mac": mac,
        "broadcast_ip": broadcast,
        "status": status,
        "message": message,
    }


async def _send_async(mac: str, broadcast: str) -> tuple[bool, str]:
    """Run the blocking socket send in a thread-friendly way (sync, but fast)."""
    return _send_packet(mac, broadcast)


@router.get("/wol/recent")
async def recent_wol(limit: int = 50) -> list[dict[str, Any]]:
    """Return recently woken devices from history."""
    limit = max(1, min(limit, 200))
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await _ensure_schema(db)
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT timestamp, mac, broadcast_ip, hostname, ip, status, message "
            "FROM wol_history ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        ) as cur:
            rows = await cur.fetchall()

    return [
        {
            "timestamp": r["timestamp"],
            "time": time.strftime("%d.%m.%Y %H:%M:%S", time.localtime(r["timestamp"])),
            "mac": r["mac"],
            "broadcast_ip": r["broadcast_ip"],
            "hostname": r["hostname"],
            "ip": r["ip"],
            "status": r["status"],
            "message": r["message"],
        }
        for r in rows
    ]