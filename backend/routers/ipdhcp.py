import asyncio
import base64
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from collectors.opnsense_client import api_get, api_post
from config import (
    IPDHCP_HISTORY_FILE,
    IPDHCP_SUBNET_PREFIX,
    PLINK_EXE,
    UNRAID_HOST,
    UNRAID_HOSTKEY,
    UNRAID_PASSWORD,
    UNRAID_SSH_MODE,
    UNRAID_USER,
)

router = APIRouter()

IP_RE = re.compile(rf"^{re.escape(IPDHCP_SUBNET_PREFIX)}\d{{1,3}}$")
CIDR_RE = re.compile(rf"({re.escape(IPDHCP_SUBNET_PREFIX)}\d{{1,3}})(?:/\d+)?")
MAC_RE = re.compile(r"^[0-9a-f]{2}(?::[0-9a-f]{2}){5}$", re.I)
HISTORY_FILE = Path(IPDHCP_HISTORY_FILE)


class StaticLeasePayload(BaseModel):
    hostname: str
    ip: str
    mac: str
    description: str = ""
    domain: str = ""
    apply: bool = True


def rows(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def add_item(items: list[dict[str, Any]], **kwargs: Any) -> None:
    ip = str(kwargs.get("ip", "")).split("/")[0]
    if not IP_RE.match(ip):
        return
    kwargs["ip"] = ip
    items.append(kwargs)


async def fetch_opnsense() -> dict[str, Any]:
    leases_data, static_data, arp_data, unbound_data = await asyncio.gather(
        api_get("dnsmasq/leases/search"),
        api_get("dnsmasq/settings/search_host"),
        api_get("diagnostics/interface/getArp"),
        api_get("unbound/settings/searchHostOverride"),
    )
    leases = rows(leases_data.get("rows"))
    static_hosts = rows(static_data.get("rows"))
    arp = rows(arp_data if isinstance(arp_data, list) else arp_data.get("data", arp_data.get("rows", [])))
    unbound = rows(unbound_data.get("rows"))

    items: list[dict[str, Any]] = []
    for r in leases:
        add_item(
            items,
            source="OPNsense DHCP",
            type="dhcp",
            ip=r.get("address", ""),
            name=r.get("hostname", ""),
            mac=str(r.get("hwaddr", "")).lower(),
            interface=r.get("if_descr", ""),
            vendor=r.get("mac_info", ""),
            status="lease",
            details=", ".join(rows(r.get("is_reserved"))),
        )
    for r in static_hosts:
        add_item(
            items,
            source="OPNsense static",
            type="dhcp-static",
            ip=r.get("ip", ""),
            name=r.get("host", ""),
            mac=str(r.get("hwaddr", "")).lower(),
            interface="",
            vendor="",
            status="static",
            details=r.get("descr", ""),
        )
    for r in arp:
        add_item(
            items,
            source="OPNsense ARP",
            type="arp",
            ip=r.get("ip", ""),
            name=r.get("hostname", ""),
            mac=str(r.get("mac", "")).lower(),
            interface=r.get("intf_description") or r.get("intf", ""),
            vendor=r.get("manufacturer", ""),
            status="expired" if r.get("expired") else "seen",
            details="",
        )
    for r in unbound:
        name = ".".join(part for part in [r.get("hostname", ""), r.get("domain", "")] if part)
        add_item(
            items,
            source="OPNsense DNS",
            type="dns",
            ip=r.get("server", ""),
            name=name,
            mac="",
            interface="",
            vendor="",
            status="dns",
            details=r.get("description", ""),
        )
    return {"items": items, "counts": {"leases": len(leases), "static": len(static_hosts), "arp": len(arp), "dns": len(unbound)}}


def sanitize_hostname(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9-]", "-", value.strip())
    cleaned = re.sub(r"-+", "-", cleaned).strip("-")
    return cleaned[:63]


async def add_static_lease(payload: StaticLeasePayload) -> dict[str, Any]:
    ip = payload.ip.strip()
    mac = payload.mac.strip().lower()
    hostname = sanitize_hostname(payload.hostname)
    description = payload.description.strip()
    domain = payload.domain.strip()

    if not IP_RE.match(ip):
        raise ValueError(f"IP must be in {IPDHCP_SUBNET_PREFIX}x")
    if not MAC_RE.match(mac):
        raise ValueError("MAC address is invalid")
    if not hostname:
        raise ValueError("Hostname is required")

    host = {
        "host": hostname,
        "domain": domain,
        "local": "0",
        "ip": ip,
        "cnames": "",
        "client_id": "",
        "hwaddr": mac,
        "lease_time": "",
        "ignore": "0",
        "set_tag": "",
        "descr": description or "Added by Homelab Dashboard",
        "comments": "",
        "aliases": "",
    }
    created = await api_post("dnsmasq/settings/add_host", {"host": host})
    applied = await api_post("dnsmasq/service/reconfigure", {}) if payload.apply else None
    return {"created": created, "applied": applied}


def run_unraid_script(script: str, timeout: int = 45) -> str:
    if not UNRAID_PASSWORD:
        raise RuntimeError("Unraid password missing")
    encoded = base64.b64encode(script.encode("utf-8")).decode("ascii")
    remote = f"echo {encoded} | base64 -d | bash"
    use_sshpass = UNRAID_SSH_MODE == "sshpass" or (UNRAID_SSH_MODE == "auto" and os.name != "nt")
    if use_sshpass and shutil.which("sshpass") and shutil.which("ssh"):
        cmd = [
            "sshpass",
            "-p",
            UNRAID_PASSWORD,
            "ssh",
            "-o",
            "StrictHostKeyChecking=accept-new",
            "-o",
            "ConnectTimeout=10",
            f"{UNRAID_USER}@{UNRAID_HOST}",
            remote,
        ]
    else:
        cmd = [PLINK_EXE, "-batch", "-ssh", "-P", "22"]
        if UNRAID_HOSTKEY:
            cmd.extend(["-hostkey", UNRAID_HOSTKEY])
        cmd.extend(["-l", UNRAID_USER, "-pw", UNRAID_PASSWORD, UNRAID_HOST, remote])

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    output = (result.stdout or "") + (result.stderr or "")
    return "\n".join(
        line
        for line in output.splitlines()
        if "Warning: Permanently added" not in line and "Keyboard-interactive" not in line
    )


async def fetch_unraid() -> dict[str, Any]:
    docker_script = r"""
ids=$(docker ps -aq 2>/dev/null | tr '\n' ' ')
if [ -n "$ids" ]; then
  timeout 25 docker inspect --format '{{.Name}}|{{.Config.Image}}|{{.State.Status}}|{{range $net,$v := .NetworkSettings.Networks}}{{printf "%s=%s/%s " $net $v.IPAddress $v.MacAddress}}{{end}}' $ids 2>/dev/null
fi
"""
    vm_script = r"""
printf 'DOMIFADDR\n'
virsh list --all --name 2>/dev/null | sed '/^$/d' | while IFS= read -r vm; do
  printf -- '--- %s ---\n' "$vm"
  virsh domifaddr "$vm" --source agent 2>/dev/null || virsh domifaddr "$vm" 2>/dev/null || true
done
printf 'DUMPXML_MACS\n'
virsh list --all --name 2>/dev/null | sed '/^$/d' | while IFS= read -r vm; do
  macs=$(virsh dumpxml "$vm" 2>/dev/null | grep -ioE "mac address='[0-9a-f:]{17}'" | sed -E "s/mac address='([^']+)'/\1/i" | tr '\n' ' ')
  printf '%s|%s\n' "$vm" "$macs"
done
"""
    docker_out, vm_out = await asyncio.gather(
        asyncio.to_thread(run_unraid_script, docker_script, 55),
        asyncio.to_thread(run_unraid_script, vm_script, 55),
    )
    items: list[dict[str, Any]] = []

    for line in docker_out.splitlines():
        if "|" not in line:
            continue
        name, image, status, networks = (line.split("|", 3) + ["", "", "", ""])[:4]
        for network, ip, mac in re.findall(rf"([A-Za-z0-9_.-]+)=({re.escape(IPDHCP_SUBNET_PREFIX)}\d{{1,3}})/([0-9a-f:]{{17}})", networks, flags=re.I):
            add_item(items, source="Unraid Docker", type="docker", ip=ip, name=name.lstrip("/"), mac=mac.lower(), interface=network, vendor="", status=status, details=image)

    current_vm = ""
    vm_macs: dict[str, set[str]] = {}
    for line in vm_out.splitlines():
        if line.startswith("--- ") and line.endswith(" ---"):
            current_vm = line[4:-4].strip()
            vm_macs.setdefault(current_vm, set())
            continue
        if "|" in line and not line.startswith("DOMIFADDR") and not line.startswith("DUMPXML"):
            vm, macs = line.split("|", 1)
            vm_macs.setdefault(vm, set()).update(m.lower() for m in re.findall(r"[0-9a-f]{2}(?::[0-9a-f]{2}){5}", macs, flags=re.I))
            continue
        if current_vm and IPDHCP_SUBNET_PREFIX in line:
            macs = re.findall(r"[0-9a-f]{2}(?::[0-9a-f]{2}){5}", line, flags=re.I)
            ip_match = CIDR_RE.search(line)
            if ip_match:
                mac = macs[0].lower() if macs else ""
                vm_macs.setdefault(current_vm, set()).add(mac)
                add_item(items, source="Unraid VM", type="vm", ip=ip_match.group(1), name=current_vm, mac=mac, interface=line.split()[0] if line.split() else "", vendor="", status="guest-agent", details="")

    unresolved = [{"name": name, "macs": sorted(m for m in macs if m)} for name, macs in sorted(vm_macs.items())]
    return {"items": items, "vm_macs": unresolved}


def consolidate(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for item in items:
        ip = item["ip"]
        row = grouped.setdefault(ip, {"ip": ip, "names": set(), "macs": set(), "interfaces": set(), "vendors": set(), "sources": set(), "types": set(), "statuses": set(), "details": set(), "items": []})
        for target, key in [("names", "name"), ("macs", "mac"), ("interfaces", "interface"), ("vendors", "vendor"), ("sources", "source"), ("types", "type"), ("statuses", "status"), ("details", "details")]:
            value = str(item.get(key, "")).strip()
            if value:
                row[target].add(value)
        row["items"].append(item)
    return sorted(({key: sorted(value) if isinstance(value, set) else value for key, value in row.items()} for row in grouped.values()), key=lambda r: [int(p) for p in r["ip"].split(".")])


def load_history() -> dict[str, Any]:
    try:
        return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"devices": {}}


def save_history(history: dict[str, Any]) -> None:
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_FILE.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")


def update_history(items: list[dict[str, Any]], now: str) -> list[dict[str, Any]]:
    history = load_history()
    devices = history.setdefault("devices", {})
    for item in items:
        mac = str(item.get("mac", "")).lower()
        if not mac or not MAC_RE.match(mac):
            continue
        entry = devices.setdefault(mac, {"mac": mac, "first_seen": now, "last_seen": now, "seen_count": 0, "names": [], "ips": [], "sources": [], "vendors": []})
        entry["last_seen"] = now
        entry["seen_count"] = int(entry.get("seen_count", 0)) + 1
        for field, key in [("names", "name"), ("ips", "ip"), ("sources", "source"), ("vendors", "vendor")]:
            value = str(item.get(key, "")).strip()
            if value and value not in entry[field]:
                entry[field].append(value)
    save_history(history)
    return sorted(devices.values(), key=lambda r: r.get("first_seen", ""), reverse=True)


@router.get("/ipdhcp/hosts")
async def get_ipdhcp_hosts():
    started = time.time()
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    errors: list[str] = []
    opn: dict[str, Any] = {"items": [], "counts": {}}
    unraid: dict[str, Any] = {"items": [], "vm_macs": []}

    results = await asyncio.gather(fetch_opnsense(), fetch_unraid(), return_exceptions=True)
    if isinstance(results[0], Exception):
        errors.append(f"OPNsense: {results[0]}")
    else:
        opn = results[0]
    if isinstance(results[1], Exception):
        errors.append(f"Unraid: {results[1]}")
    else:
        unraid = results[1]

    items = [*opn.get("items", []), *unraid.get("items", [])]
    known_by_mac = {str(item.get("mac", "")).lower(): item for item in opn.get("items", []) if item.get("mac")}
    existing_vm_ips = {(item.get("name"), item.get("ip")) for item in unraid.get("items", []) if item.get("type") == "vm"}
    for vm in unraid.get("vm_macs", []):
        for mac in vm.get("macs", []):
            match = known_by_mac.get(str(mac).lower())
            if match and (vm.get("name"), match.get("ip")) not in existing_vm_ips:
                items.append({"source": "Unraid VM", "type": "vm", "ip": match.get("ip", ""), "name": vm.get("name", ""), "mac": mac, "interface": match.get("interface", ""), "vendor": "", "status": "matched-by-mac", "details": f"matched via {match.get('source', 'OPNsense')}"})

    history = update_history(items, now)
    return {
        "generated_at": now,
        "duration_ms": round((time.time() - started) * 1000),
        "errors": errors,
        "counts": {
            "opnsense": opn.get("counts", {}),
            "unraid_items": len(unraid.get("items", [])),
            "total_items": len(items),
            "consolidated_ips": len({i["ip"] for i in items}),
        },
        "items": items,
        "hosts": consolidate(items),
        "history": history,
        "unraid_vm_macs": unraid.get("vm_macs", []),
    }


@router.post("/ipdhcp/static-lease")
async def create_static_lease(payload: StaticLeasePayload):
    try:
        return {"ok": True, "result": await add_static_lease(payload)}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
