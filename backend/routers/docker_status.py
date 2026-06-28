"""Docker container status from Unraid via SSH.

  GET /api/docker/status — container list (name, image, status, health, ports, uptime)
  GET /api/docker/stats  — CPU/Memory per container (docker stats --no-stream)

Reuses the SSH pattern from backend/routers/ipdhcp.py (run_unraid_script).
Caches results for 30s to avoid hammering Unraid SSH.
"""
import asyncio
import json
import time
from typing import Any

from fastapi import APIRouter

from routers.ipdhcp import run_unraid_script

router = APIRouter()

_CACHE: dict[str, Any] = {"status": None, "stats": None, "ts_status": 0, "ts_stats": 0}
_CACHE_TTL = 30  # seconds

DOCKER_PS_SCRIPT = r"""
docker ps -a --format '{{json .}}' 2>/dev/null
"""

DOCKER_STATS_SCRIPT = r"""
docker stats --no-stream --format '{{json .}}' 2>/dev/null
"""


def _parse_status_line(line: str) -> dict[str, Any] | None:
    line = line.strip()
    if not line or not line.startswith("{"):
        return None
    try:
        obj = json.loads(line)
    except Exception:
        return None
    # docker ps --format json fields: ID, Names, Image, Status, Ports, CreatedAt, ...
    return {
        "name": obj.get("Names") or obj.get("Name") or "",
        "id": obj.get("ID") or "",
        "image": obj.get("Image") or "",
        "status": obj.get("Status") or "",
        "running": "Up" in (obj.get("Status") or ""),
        "health": _extract_health(obj.get("Status") or ""),
        "ports": obj.get("Ports") or "",
        "created": obj.get("CreatedAt") or "",
        "uptime": _extract_uptime(obj.get("Status") or ""),
    }


def _extract_health(status: str) -> str:
    # e.g. "Up 5 minutes (health: starting)"
    if "health: healthy" in status or "(healthy)" in status:
        return "healthy"
    if "health: unhealthy" in status or "(unhealthy)" in status:
        return "unhealthy"
    if "health: starting" in status or "(health: starting)" in status:
        return "starting"
    if "Up" in status:
        return "no-healthcheck"
    return ""


def _extract_uptime(status: str) -> str:
    # e.g. "Up 2 hours", "Up 3 days", "Exited (0) 5 minutes ago"
    if not status.startswith("Up"):
        return ""
    parts = status.split(")", 1)
    return parts[0].replace("Up ", "Up ").strip()


def _parse_stats_line(line: str) -> dict[str, Any] | None:
    line = line.strip()
    if not line or not line.startswith("{"):
        return None
    try:
        obj = json.loads(line)
    except Exception:
        return None
    return {
        "name": obj.get("Name") or obj.get("Container") or "",
        "cpu": obj.get("CPUPerc") or "",
        "mem": obj.get("MemUsage") or "",
        "mem_pct": obj.get("MemPerc") or "",
        "net_io": obj.get("NetIO") or "",
        "block_io": obj.get("BlockIO") or "",
        "pids": obj.get("PIDs") or "",
    }


async def _fetch_status() -> list[dict[str, Any]]:
    out = await asyncio.to_thread(run_unraid_script, DOCKER_PS_SCRIPT, 35)
    return [c for c in (_parse_status_line(l) for l in out.splitlines()) if c]


async def _fetch_stats() -> list[dict[str, Any]]:
    out = await asyncio.to_thread(run_unraid_script, DOCKER_STATS_SCRIPT, 35)
    return [s for s in (_parse_stats_line(l) for l in out.splitlines()) if s]


@router.get("/docker/status")
async def get_docker_status():
    now = time.time()
    if _CACHE["status"] is not None and now - _CACHE["ts_status"] < _CACHE_TTL:
        return {"containers": _CACHE["status"], "cached": True, "error": None}
    try:
        containers = await _fetch_status()
        _CACHE["status"] = containers
        _CACHE["ts_status"] = now
        return {"containers": containers, "cached": False, "error": None}
    except Exception as e:
        if _CACHE["status"] is not None:
            return {"containers": _CACHE["status"], "cached": True, "error": str(e)}
        return {"containers": [], "cached": False, "error": str(e)}


@router.get("/docker/stats")
async def get_docker_stats():
    now = time.time()
    if _CACHE["stats"] is not None and now - _CACHE["ts_stats"] < _CACHE_TTL:
        return {"stats": _CACHE["stats"], "cached": True, "error": None}
    try:
        stats = await _fetch_stats()
        _CACHE["stats"] = stats
        _CACHE["ts_stats"] = now
        return {"stats": stats, "cached": False, "error": None}
    except Exception as e:
        if _CACHE["stats"] is not None:
            return {"stats": _CACHE["stats"], "cached": True, "error": str(e)}
        return {"stats": [], "cached": False, "error": str(e)}