"""VPN status router — WireGuard and OpenVPN from OPNsense API."""
from typing import Any

from fastapi import APIRouter

from collectors.opnsense_client import api_get

router = APIRouter()


def _rows(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(str(value).replace(",", "").strip() or default)
    except (ValueError, TypeError):
        return default


async def _try_endpoints(endpoints: list[str]) -> dict[str, Any] | None:
    """Try a list of OPNsense API endpoints; return first successful response."""
    for ep in endpoints:
        try:
            data = await api_get(ep)
            if data is not None:
                return data
        except Exception:
            continue
    return None


@router.get("/vpn/wireguard")
async def get_wireguard() -> dict[str, Any]:
    """Fetch WireGuard sessions/peers from OPNsense."""
    data = await _try_endpoints([
        "wireguard/general/searchSessions",
        "wireguard/client/searchSessions",
        "wireguard/server/searchSessions",
        "wireguard/general/searchPeers",
    ])

    if data is None:
        return {
            "available": False,
            "error": "WireGuard API nicht erreichbar oder Modul nicht installiert.",
            "active_peers": 0,
            "total_peers": 0,
            "peers": [],
            "data_transferred": {"rx": 0, "tx": 0},
        }

    rows = _rows(data.get("rows") if isinstance(data, dict) else data)
    peers = []
    total_rx = 0
    total_tx = 0
    active_count = 0

    for r in rows:
        # WireGuard fields vary across OPNsense versions; extract defensively
        name = r.get("name", "") or r.get("peer", "") or ""
        pubkey = r.get("public_key", "") or r.get("pubkey", "") or ""
        endpoint = r.get("endpoint", "") or r.get("peer_endpoint", "") or ""
        allowed_ips = r.get("allowed_ips", "") or ""
        enabled_raw = r.get("enabled", "1")
        enabled = str(enabled_raw) in ("1", "true", "True", "on", "yes")

        # Handshake / last seen
        handshake_raw = r.get("latest_handshake", "") or r.get("last_handshake", "") or r.get("handshake", "")
        if isinstance(handshake_raw, (int, float)) and handshake_raw:
            import time as _t
            handshake = _t.strftime("%d.%m.%Y %H:%M:%S", _t.localtime(int(handshake_raw)))
            active = (int(_t.time()) - int(handshake_raw)) < 180  # active within 3 min
        else:
            handshake = str(handshake_raw) if handshake_raw else ""
            active = False

        if active:
            active_count += 1

        # Data transferred
        rx = _to_int(r.get("rx_bytes", 0) or r.get("transfer_rx", 0))
        tx = _to_int(r.get("tx_bytes", 0) or r.get("transfer_tx", 0))
        total_rx += rx
        total_tx += tx

        peers.append({
            "name": name,
            "public_key": pubkey,
            "endpoint": endpoint,
            "allowed_ips": allowed_ips,
            "enabled": enabled,
            "active": active,
            "last_handshake": handshake,
            "rx_bytes": rx,
            "tx_bytes": tx,
        })

    return {
        "available": True,
        "active_peers": active_count,
        "total_peers": len(peers),
        "peers": peers,
        "data_transferred": {"rx": total_rx, "tx": total_tx},
    }


@router.get("/vpn/openvpn")
async def get_openvpn() -> dict[str, Any]:
    """Fetch OpenVPN server status from OPNsense."""
    data = await _try_endpoints([
        "openvpn/export/search",
        "openvpn/server/search",
        "openvpn/service/search",
        "openvpn/instances/search",
    ])

    if data is None:
        return {
            "available": False,
            "error": "OpenVPN API nicht erreichbar oder Modul nicht installiert.",
            "connected_clients": 0,
            "total_clients": 0,
            "data_transferred": {"rx": 0, "tx": 0},
            "clients": [],
            "servers": [],
        }

    rows = _rows(data.get("rows") if isinstance(data, dict) else data)
    clients = []
    servers = []
    total_rx = 0
    total_tx = 0
    connected = 0

    for r in rows:
        # Distinguish servers from client sessions heuristically
        is_server = bool(r.get("role", "") == "server" or r.get("mode", "") == "server" or r.get("vpnid", "") is not None)

        name = r.get("name", "") or r.get("description", "") or r.get("common_name", "") or ""
        common_name = r.get("common_name", "") or ""
        vpnid = str(r.get("vpnid", "") or "")
        enabled_raw = r.get("enabled", "1")
        enabled = str(enabled_raw) in ("1", "true", "True", "on", "yes")

        # Data transferred
        rx = _to_int(r.get("bytes_received", 0) or r.get("rx_bytes", 0))
        tx = _to_int(r.get("bytes_sent", 0) or r.get("tx_bytes", 0))
        total_rx += rx
        total_tx += tx

        # Connected status
        status_raw = str(r.get("status", "") or r.get("state", "")).lower()
        is_connected = "connect" in status_raw or "up" in status_raw or status_raw in ("active", "online")
        if is_connected:
            connected += 1

        client = {
            "name": name,
            "common_name": common_name,
            "vpnid": vpnid,
            "enabled": enabled,
            "connected": is_connected,
            "status": r.get("status", "") or r.get("state", "") or "",
            "real_address": r.get("real_address", "") or r.get("remote", "") or "",
            "virtual_address": r.get("virtual_address", "") or r.get("address", "") or "",
            "rx_bytes": rx,
            "tx_bytes": tx,
            "connected_since": r.get("connected_since", "") or "",
        }

        if is_server:
            servers.append(client)
        else:
            clients.append(client)

    return {
        "available": True,
        "connected_clients": connected,
        "total_clients": len(clients),
        "data_transferred": {"rx": total_rx, "tx": total_tx},
        "clients": clients,
        "servers": servers,
    }