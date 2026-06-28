"""Uptime Kuma integration via Socket.io.

Fetches monitor list and heartbeat data directly from Uptime Kuma's
Socket.io API without needing a public status page.

Configured via env: UPTIME_KUMA_HOST, UPTIME_KUMA_PORT,
UPTIME_KUMA_USERNAME, UPTIME_KUMA_PASSWORD (for login).
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


async def fetch_via_socket_io() -> dict[str, Any]:
    """Connect to Uptime Kuma via Socket.io polling and fetch monitor data."""
    base = UPTIME_KUMA_BASE.rstrip("/")
    sid_url = f"{base}/socket.io/?EIO=4&transport=polling"

    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        # 1. Get session ID
        resp = await client.get(sid_url)
        text = resp.text
        # Parse sid from response like: 0{"sid":"...","upgrades":...}
        for line in text.split("\n"):
            if line.startswith("{") and '"sid"' in line:
                data = json.loads(line)
                sid = data["sid"]
                break
        else:
            raise RuntimeError("Could not get Socket.io session")

        poll_url = f"{base}/socket.io/?EIO=4&transport=polling&sid={sid}"

        # 2. Send connect event (engine.io CONNECT)
        # Engine.IO 4: we need to send the "40" (CONNECT) message
        resp = await client.post(poll_url, content="40")
        # Read the response to get the sid confirmation
        resp = await client.get(poll_url)

        # 3. Login if credentials provided
        if UPTIME_KUMA_USERNAME and UPTIME_KUMA_PASSWORD:
            login_payload = json.dumps(["login", {
                "username": UPTIME_KUMA_USERNAME,
                "password": UPTIME_KUMA_PASSWORD,
                "token": "",
            }])
            # Socket.io message format: 42["event",data]
            msg = f"42{login_payload}"
            resp = await client.post(poll_url, content=msg)
            resp = await client.get(poll_url)

        # 4. Request monitor list via "monitorList" event
        # Send: 42["monitorList"]
        resp = await client.post(poll_url, content='42["monitorList"]')

        # 5. Poll for responses (monitor data comes back)
        monitors_raw = None
        for _ in range(5):
            await asyncio.sleep(0.5)
            resp = await client.get(poll_url)
            text = resp.text
            for line in text.split("\n"):
                if line.startswith("42"):
                    try:
                        event_data = json.loads(line[2:])
                        event_name = event_data[0] if isinstance(event_data, list) else ""
                        if event_name in ("monitorList", "monitor list"):
                            monitors_raw = event_data[1] if len(event_data) > 1 else []
                            break
                    except json.JSONDecodeError:
                        continue
            if monitors_raw is not None:
                break

        # 6. Clean up - send disconnect
        try:
            await client.post(poll_url, content="41")
        except Exception:
            pass

    if monitors_raw is None:
        raise RuntimeError("Keine Monitor-Daten erhalten — Status-Page oder Login fehlt")

    # Parse monitors
    monitors = []
    if isinstance(monitors_raw, list):
        for m in monitors_raw:
            if not isinstance(m, dict):
                continue
            mid = str(m.get("id", ""))
            status = m.get("status", 0)
            monitors.append({
                "id": mid,
                "name": m.get("name", ""),
                "type": m.get("type", ""),
                "url": m.get("url", ""),
                "status": "up" if status == 1 or status == "up" or status is True else "down" if status == 0 or status == "down" else "pending",
                "uptime_pct": round(m.get("uptime_percent", 0), 2) if m.get("uptime_percent") else 0,
                "response_time": m.get("ping") or m.get("response_time"),
                "last_check": m.get("time") or m.get("last_check"),
                "msg": m.get("msg", ""),
            })

    return monitors


async def fetch_status_page() -> dict[str, Any]:
    """Fetch a Uptime Kuma status page via the JSON endpoint (fallback)."""
    base = UPTIME_KUMA_BASE.rstrip("/")
    slug = os.getenv("UPTIME_KUMA_STATUS_SLUG", "default")
    url = f"{base}/api/status-page/{slug}"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url, follow_redirects=True)
        resp.raise_for_status()
        return resp.json()


def parse_status_page(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract monitors from status page payload."""
    monitors = []
    public = data.get("publicGroupList") or data.get("public_group_list") or []
    heartbeat_data = data.get("heartbeatList") or data.get("heartbeat_list") or {}
    if not isinstance(heartbeat_data, dict):
        heartbeat_data = {}

    for group in public if isinstance(public, list) else []:
        group_monitors = group.get("monitorList") or group.get("monitor_list") or []
        for m in group_monitors:
            mid = str(m.get("id") or m.get("monitorID") or "")
            name = m.get("name") or m.get("title") or ""
            beats = heartbeat_data.get(mid) or []
            latest = beats[-1] if beats else {}
            total = len(beats)
            up_count = sum(1 for b in beats if isinstance(b, dict) and b.get("status") in (1, "up", True))
            uptime_pct = round(up_count / total * 100, 2) if total else 0
            ping = latest.get("ping") if isinstance(latest, dict) else None
            status_val = latest.get("status", 0) if isinstance(latest, dict) else 0
            monitors.append({
                "id": mid,
                "name": name,
                "type": m.get("type", ""),
                "url": m.get("url", ""),
                "status": "up" if status_val in (1, "up", True) else "down",
                "uptime_pct": uptime_pct,
                "response_time": ping,
                "last_check": latest.get("time") if isinstance(latest, dict) else None,
                "msg": latest.get("msg", "") if isinstance(latest, dict) else "",
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

    # Try 1: Socket.io direct (works without status page)
    try:
        monitors = await fetch_via_socket_io()
    except Exception as e1:
        error = f"Socket.io: {e1}"
        # Try 2: Status page (needs public status page configured in Kuma)
        try:
            data = await fetch_status_page()
            monitors = parse_status_page(data)
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