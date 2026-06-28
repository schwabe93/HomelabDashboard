import asyncio
import json
import os
import shutil
import socket
import time
from typing import Any

import httpx
from fastapi import APIRouter

from config import STARLINK_GRPC_PORT, STARLINK_HOST

router = APIRouter()


async def tcp_check(host: str, port: int, timeout: float = 2.5) -> bool:
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=timeout)
        writer.close()
        await writer.wait_closed()
        return True
    except Exception:
        return False


async def ping_host(host: str) -> bool:
    args = ["ping", "-n", "1", "-w", "2000", host] if os.name == "nt" else ["ping", "-c", "1", "-W", "2", host]
    try:
        proc = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        return await proc.wait() == 0
    except Exception:
        return False


async def http_probe(host: str) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=3.0, follow_redirects=True) as client:
            response = await client.get(f"http://{host}/")
        return {"reachable": True, "status_code": response.status_code}
    except Exception as exc:
        return {"reachable": False, "error": str(exc)}


def find_value(value: Any, names: set[str]) -> Any:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in names:
                return item
            found = find_value(item, names)
            if found is not None:
                return found
    elif isinstance(value, list):
        for item in value:
            found = find_value(item, names)
            if found is not None:
                return found
    return None


def compact_status(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": find_value(raw, {"id", "dishId"}),
        "software_version": find_value(raw, {"softwareVersion", "software_version"}),
        "uptime_s": find_value(raw, {"uptimeS", "uptime_s"}),
        "state": find_value(raw, {"state"}),
        "alerts": find_value(raw, {"alerts"}),
        "obstruction_stats": find_value(raw, {"obstructionStats", "obstruction_stats"}),
        "pop_ping_latency_ms": find_value(raw, {"popPingLatencyMs", "pop_ping_latency_ms"}),
        "downlink_throughput_bps": find_value(raw, {"downlinkThroughputBps", "downlink_throughput_bps"}),
        "uplink_throughput_bps": find_value(raw, {"uplinkThroughputBps", "uplink_throughput_bps"}),
    }


async def grpcurl_status(host: str, port: int) -> dict[str, Any]:
    grpcurl = shutil.which("grpcurl")
    if not grpcurl:
        return {"available": False, "error": "grpcurl not installed"}

    try:
        proc = await asyncio.create_subprocess_exec(
            grpcurl,
            "-plaintext",
            "-d",
            '{"get_status":{}}',
            f"{host}:{port}",
            "SpaceX.API.Device.Device/Handle",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=8)
    except Exception as exc:
        return {"available": True, "error": str(exc)}
    text = stdout.decode("utf-8", errors="replace").strip()
    err = stderr.decode("utf-8", errors="replace").strip()
    if proc.returncode != 0:
        return {"available": True, "error": err or text or f"grpcurl exited {proc.returncode}"}
    try:
        raw = json.loads(text)
    except Exception:
        return {"available": True, "raw_text": text}
    return {"available": True, "raw": raw, "status": compact_status(raw)}


@router.get("/starlink/status")
async def get_starlink_status():
    started = time.time()
    host = STARLINK_HOST
    port = STARLINK_GRPC_PORT
    ip = None
    try:
        ip = socket.gethostbyname(host)
    except Exception:
        pass

    reachable, grpc_open, http, grpc = await asyncio.gather(
        ping_host(host),
        tcp_check(host, port),
        http_probe(host),
        grpcurl_status(host, port),
    )

    return {
        "host": host,
        "ip": ip,
        "grpc_port": port,
        "reachable": reachable,
        "grpc_open": grpc_open,
        "http": http,
        "grpc": grpc,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "duration_ms": round((time.time() - started) * 1000),
    }
