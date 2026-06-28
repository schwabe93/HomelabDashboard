"""Uptime Kuma integration.

  GET /api/uptime-kuma/status — list of monitors with name, status, uptime %, response time, last check.

Uses the public status page JSON endpoint when available. Falls back to
socket.io if a compatible client is installed; otherwise returns an empty
list with an error message so the UI can show a graceful state.

Uptime Kuma instance is expected at http://<UPTIME_KUMA_HOST>:<port>.
Configured via env: UPTIME_KUMA_HOST, UPTIME_KUMA_PORT, UPTIME_KUMA_STATUS_SLUG.
"""
import asyncio
import json
import os
import time
from typing import Any

import httpx
from fastapi import APIRouter

router = APIRouter()

UPTIME_KUMA_HOST = os.getenv("UPTIME_KUMA_HOST", "192.168.188.106")
UPTIME_KUMA_PORT = int(os.getenv("UPTIME_KUMA_PORT", "3001"))
UPTIME_KUMA_STATUS_SLUG = os.getenv("UPTIME_KUMA_STATUS_SLUG", "default")
UPTIME_KUMA_BASE = os.getenv("UPTIME_KUMA_BASE", f"http://{UPTIME_KUMA_HOST}:{UPTIME_KUMA_PORT}")

_CACHE: dict[str, Any] = {"data": None, "ts": 0}
_CACHE_TTL = 30


def _extract_heartbeat_stats(beat: dict[str, Any]) -> dict[str, Any]:
    """Pull status/ping/time from a heartbeat object (Uptime Kuma shape)."""
    status = beat.get("status", 0)
    return {
        "up": status == 1 or status == "up" or status is True,
        "ping": beat.get("ping"),
        "time": beat.get("time"),
        "msg": beat.get("msg", ""),
    }


async def fetch_status_page() -> dict[str, Any]:
    """Fetch a Uptime Kuma status page via the JSON endpoint."""
    base = UPTIME_KUMA_BASE.rstrip("/")
    url = f"{base}/api/status-page/{UPTIME_KUMA_STATUS_SLUG}"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url, follow_redirects=True)
        resp.raise_for_status()
        return resp.json()


async def fetch_legacy_status() -> dict[str, Any]:
    """Try the older /metrics or /api/status-page fallback endpoints."""
    base = UPTIME_KUMA_BASE.rstrip("/")
    candidates = [
        f"{base}/api/status-page/heartbeat/{UPTIME_KUMA_STATUS_SLUG}",
        f"{base}/status/{UPTIME_KUMA_STATUS_SLUG}?json=1",
    ]
    async with httpx.AsyncClient(timeout=10) as client:
        for url in candidates:
            try:
                resp = await client.get(url, follow_redirects=True)
                if resp.status_code == 200:
                    return resp.json()
            except Exception:
                continue
    raise RuntimeError("Kein Uptime Kuma Status-Endpunkt erreichbar")


def parse_monitors(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Best-effort extraction of monitor info from the status page payload."""
    monitors: list[dict[str, Any]] = []
    # Uptime Kuma status-page payload has different shapes by version.
    public = data.get("publicGroupList") or data.get("public_group_list") or []
    heartbeat_data = data.get("heartbeatList") or data.get("heartbeat_list") or {}
    if isinstance(heartbeat_data, dict) is False:
        heartbeat_data = {}

    for group in public if isinstance(public, list) else []:
        group_monitors = group.get("monitorList") or group.get("monitor_list") or []
        for m in group_monitors:
            mid = str(m.get("id") or m.get("monitorID") or "")
            name = m.get("name") or m.get("title") or ""
            beats = heartbeat_data.get(mid) or []
            latest = beats[-1] if beats else {}
            stats = _extract_heartbeat_stats(latest) if isinstance(latest, dict) else {}
            # Compute uptime percentage from recent beats.
            total = len(beats)
            up_count = sum(1 for b in beats if isinstance(b, dict) and (b.get("status") in (1, "up", True)))
            uptime_pct = round(up_count / total * 100, 2) if total else 0
            monitors.append({
                "id": mid,
                "name": name,
                "type": m.get("type") or "",
                "url": m.get("url") or "",
                "status": "up" if stats.get("up") else "down",
                "uptime_pct": uptime_pct,
                "response_time": stats.get("ping"),
                "last_check": stats.get("time"),
                "msg": stats.get("msg", ""),
            })

    # Fallback: if payload directly contains a "monitorList".
    if not monitors:
        direct = data.get("monitorList") or data.get("monitors") or []
        if isinstance(direct, list):
            for m in direct:
                monitors.append({
                    "id": str(m.get("id") or ""),
                    "name": m.get("name") or "",
                    "type": m.get("type") or "",
                    "url": m.get("url") or "",
                    "status": "up" if m.get("status") in (1, "up", True) else "down",
                    "uptime_pct": m.get("uptime_pct") or 0,
                    "response_time": m.get("response_time") or m.get("ping"),
                    "last_check": m.get("last_check") or m.get("time"),
                    "msg": m.get("msg", ""),
                })
    return monitors


@router.get("/uptime-kuma/status")
async def get_uptime_kuma_status():
    now = time.time()
    if _CACHE["data"] is not None and now - _CACHE["ts"] < _CACHE_TTL:
        d = _CACHE["data"]
        return {"monitors": d.get("monitors", []), "summary": d.get("summary", {}), "cached": True, "error": None}

    try:
        data = await fetch_status_page()
        monitors = parse_monitors(data)
        summary = {
            "total": len(monitors),
            "up": sum(1 for m in monitors if m["status"] == "up"),
            "down": sum(1 for m in monitors if m["status"] == "down"),
        }
        result = {"monitors": monitors, "summary": summary, "cached": False, "error": None}
        _CACHE["data"] = result
        _CACHE["ts"] = now
        return result
    except Exception as e:
        # Try legacy endpoints as a fallback.
        try:
            data = await fetch_legacy_status()
            monitors = parse_monitors(data)
            summary = {
                "total": len(monitors),
                "up": sum(1 for m in monitors if m["status"] == "up"),
                "down": sum(1 for m in monitors if m["status"] == "down"),
            }
            result = {"monitors": monitors, "summary": summary, "cached": False, "error": None}
            _CACHE["data"] = result
            _CACHE["ts"] = now
            return result
        except Exception as e2:
            return {
                "monitors": [],
                "summary": {"total": 0, "up": 0, "down": 0},
                "cached": False,
                "error": f"Uptime Kuma nicht erreichbar unter {UPTIME_KUMA_BASE}: {e2}",
            }