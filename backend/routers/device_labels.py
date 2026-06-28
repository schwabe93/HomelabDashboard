"""Device labels — custom names/icons stored per MAC address.

Provides:
  GET    /api/devices/labels        — all custom labels
  POST   /api/devices/label          — upsert {mac, label, icon}
  DELETE /api/devices/label/{mac}    — remove a label

Uses aiosqlite, same pattern as database.py.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import aiosqlite
from config import DATABASE_PATH

router = APIRouter()

MAC_RE = r"^[0-9a-f]{2}(?::[0-9a-f]{2}){5}$"


class LabelPayload(BaseModel):
    mac: str = Field(..., pattern=MAC_RE)
    label: str = Field("", max_length=64)
    icon: str = Field("", max_length=16)


async def ensure_table() -> None:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS device_labels (
                mac      TEXT PRIMARY KEY,
                label    TEXT NOT NULL DEFAULT '',
                icon     TEXT NOT NULL DEFAULT '',
                updated_at INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        await db.commit()


@router.get("/devices/labels")
async def get_labels():
    await ensure_table()
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT mac, label, icon, updated_at FROM device_labels ORDER BY label ASC, mac ASC"
        ) as cur:
            rows = await cur.fetchall()
    return {
        "labels": [
            {
                "mac": r["mac"],
                "label": r["label"],
                "icon": r["icon"],
                "updated_at": r["updated_at"],
            }
            for r in rows
        ]
    }


@router.post("/devices/label")
async def set_label(payload: LabelPayload):
    mac = payload.mac.strip().lower()
    label = payload.label.strip()
    icon = payload.icon.strip()
    if not label and not icon:
        raise HTTPException(status_code=400, detail="Label oder Icon erforderlich")
    await ensure_table()
    import time
    now = int(time.time())
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "INSERT INTO device_labels (mac, label, icon, updated_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(mac) DO UPDATE SET label=excluded.label, icon=excluded.icon, updated_at=excluded.updated_at",
            (mac, label, icon, now),
        )
        await db.commit()
    return {"ok": True, "mac": mac, "label": label, "icon": icon}


@router.delete("/devices/label/{mac}")
async def delete_label(mac: str):
    mac = mac.strip().lower()
    await ensure_table()
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cur = await db.execute("DELETE FROM device_labels WHERE mac = ?", (mac,))
        await db.commit()
        deleted = cur.rowcount
    return {"ok": True, "deleted": deleted, "mac": mac}