"""Port Forwarding / NAT rules overview router — fetches from OPNsense API."""
from typing import Any

from fastapi import APIRouter

from collectors.opnsense_client import api_get

router = APIRouter()


def _rows(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


@router.get("/nat/rules")
async def get_nat_rules() -> list[dict[str, Any]]:
    """Fetch port-forward rules from OPNsense and return a formatted list."""
    try:
        data = await api_get("firewall/filter/searchPortForward")
        raw = _rows(data.get("rows"))
    except Exception as e:
        return []

    result = []
    for r in raw:
        # OPNsense port-forward fields vary; extract defensively
        protocol = r.get("protocol", "")
        # source: may be a network or "any"
        src = r.get("source", {})
        source = ""
        if isinstance(src, dict):
            source = src.get("network") or src.get("address") or src.get("any", "any") or "any"
        elif isinstance(src, str):
            source = src
        else:
            source = str(src) if src else "any"

        dst = r.get("destination", {})
        destination = ""
        dst_port = ""
        if isinstance(dst, dict):
            destination = dst.get("network") or dst.get("address") or "any"
            dst_port = str(dst.get("port", "") or "")
        elif isinstance(dst, str):
            destination = dst

        target = r.get("target", {})
        if isinstance(target, dict):
            target_ip = target.get("network") or target.get("address") or ""
            target_port = str(target.get("port", "") or "")
        else:
            target_ip = str(target) if target else ""
            target_port = str(r.get("target_port", "") or "")

        target_str = target_ip
        if target_port:
            target_str = f"{target_ip}:{target_port}" if target_ip else target_port

        description = r.get("description", "") or r.get("descr", "") or ""
        enabled_raw = r.get("enabled", "1")
        enabled = str(enabled_raw) in ("1", "true", "True", "on", "yes")

        result.append({
            "uuid": r.get("uuid", ""),
            "protocol": protocol or "any",
            "source": source,
            "destination": destination,
            "port": dst_port,
            "target": target_str,
            "description": description,
            "enabled": enabled,
            "interface": r.get("interface", ""),
            "ipprotocol": r.get("ipprotocol", ""),
        })

    # enabled first, then by description
    result.sort(key=lambda x: (not x["enabled"], x["description"].lower()))
    return result


@router.get("/nat/rules/raw")
async def get_nat_rules_raw() -> dict[str, Any]:
    """Return raw OPNsense port-forward response for debugging."""
    try:
        return await api_get("firewall/filter/searchPortForward")
    except Exception as e:
        return {"error": str(e)}