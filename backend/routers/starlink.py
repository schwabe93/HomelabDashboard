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
    alerts_raw = find_value(raw, {"alerts"}) or {}
    obstruction = find_value(raw, {"obstructionStats", "obstruction_stats"}) or {}
    device_info = find_value(raw, {"deviceInfo", "device_info"}) or {}
    device_state = find_value(raw, {"deviceState", "device_state"}) or {}
    return {
        "id": find_value(raw, {"id", "dishId"}),
        "software_version": find_value(raw, {"softwareVersion", "software_version"}),
        "hardware_version": find_value(raw, {"hardwareVersion", "hardware_version"}),
        "country_code": find_value(raw, {"countryCode", "country_code"}),
        "utc_offset_s": find_value(raw, {"utcOffsetS", "utc_offset_s"}),
        "uptime_s": find_value(raw, {"uptimeS", "uptime_s"}),
        "bootcount": find_value(raw, {"bootcount"}),
        "state": find_value(raw, {"state"}),
        "alerts": {
            "motors_stuck": alerts_raw.get("motorsStuck", False),
            "thermal_throttle": alerts_raw.get("thermalThrottle", False),
            "thermal_shutdown": alerts_raw.get("thermalShutdown", False),
            "mast_not_near_vertical": alerts_raw.get("mastNotNearVertical", False),
            "slow_ethernet_speeds": alerts_raw.get("slowEthernetSpeeds", False),
            "install_pending": alerts_raw.get("installPending", False),
            "is_heating": alerts_raw.get("isHeating", False),
            "power_supply_thermal_throttle": alerts_raw.get("powerSupplyThermalThrottle", False),
            "is_power_save_idle": alerts_raw.get("isPowerSaveIdle", False),
            "moving_fast_while_not_mobile": alerts_raw.get("movingFastWhileNotMobile", False),
            "slow_location_speeds": alerts_raw.get("slowLocationSpeeds", False),
        },
        "obstruction_stats": {
            "fraction_obstructed": obstruction.get("fractionObstructed", obstruction.get("fraction_obstructed")),
            "currently_obstructed": obstruction.get("currentlyObstructed", obstruction.get("currently_obstructed")),
            "valid_s": obstruction.get("validS", obstruction.get("valid_s")),
            "wedge_fraction_obstructed": obstruction.get("wedgeFractionObstructed", obstruction.get("wedge_fraction_obstructed")),
            "wedge_abs_fraction_obstructed": obstruction.get("wedgeAbsFractionObstructed", obstruction.get("wedge_abs_fraction_obstructed")),
            "time_obstructed": obstruction.get("timeObstructed", obstruction.get("time_obstructed")),
            "patches_obstructed": obstruction.get("patchesObstructed", obstruction.get("patches_obstructed")),
            "avg_prolonged_obstruction_interval_s": obstruction.get("avgProlongedObstructionIntervalS", obstruction.get("avg_prolonged_obstruction_interval_s")),
            "time_obstructed_pct": obstruction.get("timeObstructedPct", obstruction.get("time_obstructed_pct")),
        },
        "pop_ping_latency_ms": find_value(raw, {"popPingLatencyMs", "pop_ping_latency_ms"}),
        "pop_ping_drop_rate": find_value(raw, {"popPingDropRate", "pop_ping_drop_rate"}),
        "initial_ping_drop_rate": find_value(raw, {"initialPingDropRate", "initial_ping_drop_rate"}),
        "downlink_throughput_bps": find_value(raw, {"downlinkThroughputBps", "downlink_throughput_bps"}),
        "uplink_throughput_bps": find_value(raw, {"uplinkThroughputBps", "uplink_throughput_bps"}),
        "seconds_to_first_nonempty_slot": find_value(raw, {"secondsToFirstNonemptySlot", "seconds_to_first_nonempty_slot"}),
        "gps_stats": find_value(raw, {"gpsStats", "gps_stats"}),
        "mobile_country_code": find_value(raw, {"mobileCountryCode", "mobile_country_code"}),
        "mobile_network_code": find_value(raw, {"mobileNetworkCode", "mobile_network_code"}),
    }


def compact_history(raw: dict[str, Any]) -> dict[str, Any]:
    """Extract recent history data from get_history response."""
    current = find_value(raw, {"current"})
    
    def extract_array(name_set: set[str]) -> list:
        val = find_value(raw, name_set)
        if val is None:
            return []
        if isinstance(val, list):
            return val
        return [val]
    
    ping_drop = extract_array({"popPingDropRate", "pop_ping_drop_rate"})
    ping_latency = extract_array({"popPingLatencyMs", "pop_ping_latency_ms"})
    downlink = extract_array({"downlinkThroughputBps", "downlink_throughput_bps"})
    uplink = extract_array({"uplinkThroughputBps", "uplink_throughput_bps"})
    snr = extract_array({"snr"})
    
    # Take last 60 samples (1 hour worth at 1min interval, or ~15min at 15s)
    samples = 60
    if current and isinstance(current, (int, float)) and current > 0:
        start = max(0, int(current) - samples)
    else:
        start = max(0, len(ping_drop) - samples) if ping_drop else 0
    
    def slice_arr(arr):
        if not arr or start >= len(arr):
            return []
        return arr[start:start + samples]
    
    pd = slice_arr(ping_drop)
    pl = slice_arr(ping_latency)
    dl = slice_arr(downlink)
    ul = slice_arr(uplink)
    sn = slice_arr(snr)
    
    # Compute summary stats
    def avg(arr):
        vals = [v for v in arr if v is not None and isinstance(v, (int, float))]
        return round(sum(vals) / len(vals), 2) if vals else None
    
    def pct(arr, p):
        vals = sorted([v for v in arr if v is not None and isinstance(v, (int, float))])
        if not vals:
            return None
        idx = int(len(vals) * p / 100)
        return round(vals[min(idx, len(vals) - 1)], 2)
    
    return {
        "current": current,
        "samples": len(pd),
        "ping_drop_rate": pd,
        "ping_latency_ms": pl,
        "downlink_bps": dl,
        "uplink_bps": ul,
        "snr": sn,
        "summary": {
            "avg_latency_ms": avg(pl),
            "max_latency_ms": max([v for v in pl if isinstance(v, (int, float))], default=None),
            "min_latency_ms": min([v for v in pl if isinstance(v, (int, float))], default=None),
            "avg_drop_rate": avg(pd),
            "max_drop_rate": max([v for v in pd if isinstance(v, (int, float))], default=None),
            "avg_downlink_bps": avg(dl),
            "avg_uplink_bps": avg(ul),
            "p95_latency_ms": pct(pl, 95),
            "p99_latency_ms": pct(pl, 99),
            "unavailable_pct": round(sum(1 for v in pd if isinstance(v, (int, float)) and v >= 1) / max(len(pd), 1) * 100, 1) if pd else None,
        },
    }


async def grpcurl_call(host: str, port: int, method: str, payload: str, timeout: float = 8) -> dict[str, Any]:
    """Generic grpcurl call to Starlink dish."""
    grpcurl = shutil.which("grpcurl")
    if not grpcurl:
        return {"available": False, "error": "grpcurl not installed"}
    
    try:
        proc = await asyncio.create_subprocess_exec(
            grpcurl,
            "-plaintext",
            "-d",
            payload,
            f"{host}:{port}",
            "SpaceX.API.Device.Device/Handle",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        return {"available": True, "error": "timeout"}
    except Exception as exc:
        return {"available": True, "error": str(exc)}
    
    text = stdout.decode("utf-8", errors="replace").strip()
    err = stderr.decode("utf-8", errors="replace").strip()
    if proc.returncode != 0:
        return {"available": True, "error": err or text or f"grpcurl exited {proc.returncode}"}
    try:
        return {"available": True, "raw": json.loads(text)}
    except Exception:
        return {"available": True, "raw_text": text}


async def grpcurl_status(host: str, port: int) -> dict[str, Any]:
    result = await grpcurl_call(host, port, "get_status", '{"get_status":{}}')
    if not result.get("available"):
        return result
    if result.get("raw"):
        raw = result["raw"]
        return {"available": True, "raw": raw, "status": compact_status(raw)}
    return result


async def grpcurl_history(host: str, port: int) -> dict[str, Any]:
    result = await grpcurl_call(host, port, "get_history", '{"get_history":{}}', timeout=10)
    if not result.get("available"):
        return result
    if result.get("raw"):
        raw = result["raw"]
        return {"available": True, "raw": raw, "history": compact_history(raw)}
    return result


async def grpcurl_ping(host: str, port: int) -> dict[str, Any]:
    """Run a simple ping test via grpcurl."""
    result = await grpcurl_call(host, port, "get_status", '{"get_status":{}}', timeout=5)
    if not result.get("available"):
        return result
    if result.get("raw"):
        latency = find_value(result["raw"], {"popPingLatencyMs", "pop_ping_latency_ms"})
        drop = find_value(result["raw"], {"popPingDropRate", "pop_ping_drop_rate"})
        return {"available": True, "latency_ms": latency, "drop_rate": drop}
    return result


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

    reachable, grpc_open, http, grpc, history = await asyncio.gather(
        ping_host(host),
        tcp_check(host, port),
        http_probe(host),
        grpcurl_status(host, port),
        grpcurl_history(host, port),
    )

    # Extract alerts for convenience
    alerts = {}
    if grpc.get("status", {}).get("alerts"):
        alerts = grpc["status"]["alerts"]

    return {
        "host": host,
        "ip": ip,
        "grpc_port": port,
        "reachable": reachable,
        "grpc_open": grpc_open,
        "http": http,
        "grpc": grpc,
        "history": history,
        "alerts": alerts,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "duration_ms": round((time.time() - started) * 1000),
    }


@router.get("/starlink/history")
async def get_starlink_history():
    started = time.time()
    host = STARLINK_HOST
    port = STARLINK_GRPC_PORT
    
    history = await grpcurl_history(host, port)
    
    return {
        "host": host,
        "history": history,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "duration_ms": round((time.time() - started) * 1000),
    }