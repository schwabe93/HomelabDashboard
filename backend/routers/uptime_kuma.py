"""Uptime Kuma integration via python-socketio.

Connects directly to Uptime Kuma's Socket.io API to fetch monitor list
and heartbeat data. No public status page needed.

Config: UPTIME_KUMA_HOST, UPTIME_KUMA_PORT, UPTIME_KUMA_USERNAME, UPTIME_KUMA_PASSWORD
"""
import asyncio
import json
import os
import time
from typing import Any

import httpx
from fastapi import APIRouter

router = APIRouter()

UPTIME_KUMA_HOST = os.getenv("UPTIME_KUMA_HOST", "192.168.188.23")
UPTIME_KUMA_PORT = int(os.getenv("UPTIME_KUMA_PORT", "3001"))
UPTIME_KUMA_BASE = os.getenv("UPTIME_KUMA_BASE", f"http://{UPTIME_KUMA_HOST}:{UPTIME_KUMA_PORT}")
UPTIME_KUMA_USERNAME = os.getenv("UPTIME_KUMA_USERNAME", "")
UPTIME_KUMA_PASSWORD = os.getenv("UPTIME_KUMA_PASSWORD", "")

_CACHE: dict[str, Any] = {"data": None, "ts": 0}
_CACHE_TTL = 30


async def fetch_via_socketio() -> list[dict[str, Any]]:
    """Connect to Uptime Kuma via Socket.io and fetch monitor list."""
    try:
        import socketio
    except ImportError:
        raise RuntimeError("python-socketio not installed")

    base = UPTIME_KUMA_BASE.rstrip("/")
    sio = socketio.AsyncSimpleClient()
    monitors = []
    got_data = asyncio.Event()

    async def on_monitor_list(data):
        nonlocal monitors
        if isinstance(data, list):
            monitors = [m for m in data if isinstance(m, dict)]
        elif isinstance(data, dict):
            monitors = [m for m in data.values() if isinstance(m, dict)]
        got_data.set()

    await sio.connect(base, transports=["polling"], socketio_path="/socket.io")
    sio.on("monitorList", on_monitor_list)

    # Login if credentials provided
    if UPTIME_KUMA_USERNAME and UPTIME_KUMA_PASSWORD:
        await sio.emit("login", {
            "username": UPTIME_KUMA_USERNAME,
            "password": UPTIME_KUMA_PASSWORD,
            "token": "",
        })
        await asyncio.sleep(1)

    # Request monitor list
    await sio.emit("monitorList")

    # Wait for response
    try:
        await asyncio.wait_for(got_data.wait(), timeout=5)
    except asyncio.TimeoutError:
        pass

    await sio.disconnect()

    if not monitors:
        raise RuntimeError("Keine Monitor-Daten erhalten")

    # Parse
    result = []
    for m in monitors:
        mid = str(m.get("id", ""))
        status = m.get("status", 0)
        result.append({
            "id": mid,
            "name": m.get("name", ""),
            "type": m.get("type", ""),
            "url": m.get("url", ""),
            "hostname": m.get("hostname", ""),
            "port": m.get("port"),
            "status": "up" if status == 1 or status is True else "down" if status == 0 or status is False else "pending",
            "uptime_pct": round(float(m.get("uptime_percent", 0) or 0), 2),
            "response_time": m.get("ping") or m.get("response_time"),
            "last_check": m.get("time") or m.get("last_check"),
            "msg": m.get("msg", ""),
            "active": m.get("active", False),
        })
    return result


async def fetch_status_page() -> list[dict[str, Any]]:
    """Fallback: fetch status page JSON."""
    base = UPTIME_KUMA_BASE.rstrip("/")
    slug = os.getenv("UPTIME_KUMA_STATUS_SLUG", "default")
    url = f"{base}/api/status-page/{slug}"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url, follow_redirects=True)
        resp.raise_for_status()
        data = resp.json()

    monitors = []
    public = data.get("publicGroupList") or data.get("public_group_list") or []
    heartbeat_data = data.get("heartbeatList") or data.get("heartbeat_list") or {}
    if not isinstance(heartbeat_data, dict):
        heartbeat_data = {}

    for group in public if isinstance(public, list) else []:
        for m in (group.get("monitorList") or group.get("monitor_list") or []):
            mid = str(m.get("id") or m.get("monitorID") or "")
            beats = heartbeat_data.get(mid) or []
            latest = beats[-1] if beats else {}
            total = len(beats)
            up_count = sum(1 for b in beats if isinstance(b, dict) and b.get("status") in (1, "up", True))
            monitors.append({
                "id": mid,
                "name": m.get("name") or m.get("title") or "",
                "type": m.get("type", ""),
                "url": m.get("url", ""),
                "status": "up" if latest.get("status") in (1, "up", True) else "down",
                "uptime_pct": round(up_count / total * 100, 2) if total else 0,
                "response_time": latest.get("ping"),
                "last_check": latest.get("time"),
                "msg": latest.get("msg", ""),
            })
    return monitors


@router.get("/uptime-kuma/status")
async def get_uptime_kuma_status():
    now = time.time()
    if _CACHE["data"] is not None and now - _CACHE["ts"] < _CACHE_TTL:
        d = _CACHE["data"]
        return {"monitors": d.get("monitors", []), "summary": d.get("summary", {}), "cached": True, "error": None}

    monitors = []
    error = None

    # Try 1: Socket.io direct
    try:
        monitors = await fetch_via_socketio()
    except Exception as e1:
        error = f"Socket.io: {e1}"
        # Try 2: Status page
        try:
            monitors = await fetch_status_page()
            error = None
        except Exception as e2:
            error = f"{error} | Status-Page: {e2}"

    summary = {
        "total": len(monitors),
        "up": sum(1 for m in monitors if m.get("status") == "up"),
        "down": sum(1 for m in monitors if m.get("status") == "down"),
    }
    result = {"monitors": monitors, "summary": summary, "cached": False, "error": error}
    _CACHE["data"] = result
    _CACHE["ts"] = now
    return result