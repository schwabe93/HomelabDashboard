"""Proxmox VM/CT status via SSH.

  GET  /api/proxmox/vms            — list of VMs and CTs (qm list + pct list)
  GET  /api/proxmox/status/{vmid}  — status of a single VM or CT
  POST /api/proxmox/{action}/{vmid} — start/stop a VM or CT (action in start|stop|restart)

Caches VM list for 60s.
"""
import asyncio
import base64
import os
import re
import shutil
import subprocess
import time
from typing import Any

from fastapi import APIRouter, HTTPException

router = APIRouter()

# Proxmox SSH credentials — read from env (with sensible defaults).
PROXMOX_HOST = os.getenv("PROXMOX_HOST", "192.168.188.20")
PROXMOX_USER = os.getenv("PROXMOX_USER", "root")
PROXMOX_PASSWORD = os.getenv("PROXMOX_PASSWORD", "Dachgeschoss93!")
PROXMOX_SSH_MODE = os.getenv("PROXMOX_SSH_MODE", "auto").lower()
PROXMOX_PLINK_EXE = os.getenv("PLINK_EXE", "plink.exe")

_CACHE: dict[str, Any] = {"vms": None, "ts": 0}
_CACHE_TTL = 60  # seconds


def run_proxmox_script(script: str, timeout: int = 30) -> str:
    if not PROXMOX_PASSWORD:
        raise RuntimeError("Proxmox password missing")
    encoded = base64.b64encode(script.encode("utf-8")).decode("ascii")
    remote = f"echo {encoded} | base64 -d | bash"
    use_sshpass = PROXMOX_SSH_MODE == "sshpass" or (PROXMOX_SSH_MODE == "auto" and os.name != "nt")
    if use_sshpass and shutil.which("sshpass") and shutil.which("ssh"):
        cmd = [
            "sshpass",
            "-p",
            PROXMOX_PASSWORD,
            "ssh",
            "-o", "StrictHostKeyChecking=accept-new",
            "-o", "ConnectTimeout=10",
            f"{PROXMOX_USER}@{PROXMOX_HOST}",
            remote,
        ]
    else:
        cmd = [PROXMOX_PLINK_EXE, "-batch", "-ssh", "-P", "22",
               "-l", PROXMOX_USER, "-pw", PROXMOX_PASSWORD, PROXMOX_HOST, remote]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    output = (result.stdout or "") + (result.stderr or "")
    return "\n".join(
        line for line in output.splitlines()
        if "Warning: Permanently added" not in line and "Keyboard-interactive" not in line
    )


def parse_vm_list(output: str) -> list[dict[str, Any]]:
    """Parse `qm list` output. Columns: VMID Name Status Memory(GB) Cores Bootdisk PID"""
    rows: list[dict[str, Any]] = []
    lines = output.splitlines()
    # find header line containing 'VMID'
    start = 0
    for i, line in enumerate(lines):
        if "VMID" in line and ("Name" in line or "STATUS" in line):
            start = i + 1
            break
    for line in lines[start:]:
        line = line.strip()
        if not line or line.startswith("Total"):
            continue
        parts = re.split(r"\s+", line)
        if not parts or not parts[0].isdigit():
            continue
        vmid = parts[0]
        name = parts[1] if len(parts) > 1 else ""
        status = parts[2] if len(parts) > 2 else ""
        mem = parts[3] if len(parts) > 3 else ""
        cores = parts[4] if len(parts) > 4 else ""
        rows.append({
            "vmid": vmid,
            "name": name,
            "status": status.lower(),
            "type": "vm",
            "memory": mem,
            "cores": cores,
            "uptime": "",
        })
    return rows


def parse_ct_list(output: str) -> list[dict[str, Any]]:
    """Parse `pct list` output. Columns: VMID Status Name ... (varies by version)."""
    rows: list[dict[str, Any]] = []
    lines = output.splitlines()
    start = 0
    for i, line in enumerate(lines):
        if "VMID" in line:
            start = i + 1
            break
    for line in lines[start:]:
        line = line.strip()
        if not line:
            continue
        parts = re.split(r"\s+", line)
        if not parts or not parts[0].isdigit():
            continue
        vmid = parts[0]
        # pct list layout: VMID STATUS NAME (status before name in newer versions)
        if len(parts) >= 3:
            status = parts[1].lower()
            name = parts[2]
        elif len(parts) == 2:
            status = parts[1].lower()
            name = ""
        else:
            status = ""
            name = ""
        rows.append({
            "vmid": vmid,
            "name": name,
            "status": status,
            "type": "ct",
            "memory": "",
            "cores": "",
            "uptime": "",
        })
    return rows


def detect_type(vmid: str) -> str:
    """Best-effort: assume VM unless a CT is found. Caller passes the cache."""
    return "vm"


async def fetch_vms() -> list[dict[str, Any]]:
    script = "qm list 2>/dev/null; echo '---PCT---'; pct list 2>/dev/null"
    out = await asyncio.to_thread(run_proxmox_script, script, 35)
    vm_part, ct_part = out, ""
    if "---PCT---" in out:
        vm_part, ct_part = out.split("---PCT---", 1)
    vms = parse_vm_list(vm_part)
    cts = parse_ct_list(ct_part)
    return [*vms, *cts]


@router.get("/proxmox/vms")
async def get_vms():
    now = time.time()
    if _CACHE["vms"] is not None and now - _CACHE["ts"] < _CACHE_TTL:
        return {"vms": _CACHE["vms"], "cached": True, "error": None}
    try:
        vms = await fetch_vms()
        _CACHE["vms"] = vms
        _CACHE["ts"] = now
        return {"vms": vms, "cached": False, "error": None}
    except Exception as e:
        if _CACHE["vms"] is not None:
            return {"vms": _CACHE["vms"], "cached": True, "error": str(e)}
        return {"vms": [], "cached": False, "error": str(e)}


@router.get("/proxmox/status/{vmid}")
async def get_status(vmid: str):
    # Determine type from cache if possible.
    vtype = "vm"
    if _CACHE["vms"]:
        for v in _CACHE["vms"]:
            if str(v.get("vmid")) == str(vmid):
                vtype = v.get("type", "vm")
                break
    cmd = "pct status" if vtype == "ct" else "qm status"
    script = f"{cmd} {vmid} 2>/dev/null"
    try:
        out = await asyncio.to_thread(run_proxmox_script, script, 25)
        return {"vmid": vmid, "type": vtype, "raw": out.strip(), "error": None}
    except Exception as e:
        return {"vmid": vmid, "type": vtype, "raw": "", "error": str(e)}


@router.post("/proxmox/{action}/{vmid}")
async def perform_action(action: str, vmid: str):
    if action not in ("start", "stop", "restart", "shutdown"):
        raise HTTPException(status_code=400, detail=f"Unbekannte Aktion: {action}")
    vtype = "vm"
    if _CACHE["vms"]:
        for v in _CACHE["vms"]:
            if str(v.get("vmid")) == str(vmid):
                vtype = v.get("type", "vm")
                break
    cmd = "pct" if vtype == "ct" else "qm"
    script = f"{cmd} {action} {vmid} 2>&1"
    try:
        out = await asyncio.to_thread(run_proxmox_script, script, 35)
        # Invalidate cache so next fetch shows new state.
        _CACHE["ts"] = 0
        return {"ok": True, "vmid": vmid, "action": action, "type": vtype, "output": out.strip()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e