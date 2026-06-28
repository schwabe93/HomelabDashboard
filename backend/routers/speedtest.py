"""Speedtest integration router — runs speedtest CLI and stores results in SQLite."""
import re
import shutil
import subprocess
import time
from typing import Any

import aiosqlite
from fastapi import APIRouter

from config import DATABASE_PATH

router = APIRouter()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS speedtest_results (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp     INTEGER NOT NULL,
    download_mbps REAL NOT NULL DEFAULT 0,
    upload_mbps   REAL NOT NULL DEFAULT 0,
    ping_ms       REAL NOT NULL DEFAULT 0,
    jitter_ms    REAL DEFAULT 0,
    isp           TEXT DEFAULT '',
    server_id     TEXT DEFAULT '',
    server_name   TEXT DEFAULT '',
    raw_output    TEXT DEFAULT '',
    source        TEXT DEFAULT 'speedtest-cli'
);
CREATE INDEX IF NOT EXISTS idx_speedtest_ts ON speedtest_results(timestamp);
"""


async def _ensure_schema(db: aiosqlite.Connection) -> None:
    for stmt in _SCHEMA.strip().split(";"):
        s = stmt.strip()
        if s:
            await db.execute(s)
    await db.commit()


def _find_speedtest_binary() -> str | None:
    """Locate a speedtest CLI binary. Prefer Ookla 'speedtest', fall back to 'speedtest-cli'."""
    for name in ("speedtest", "speedtest-cli"):
        path = shutil.which(name)
        if path:
            return path
    return None


# ── Parsers ──────────────────────────────────────────────────────
_FLOAT_RE = r"([0-9]+(?:\.[0-9]+)?)"


def _parse_speedtest_cli(output: str) -> dict[str, Any]:
    """Parse python 'speedtest-cli' JSON-ish / text output."""
    # Try JSON output first (--json flag used)
    import json
    try:
        data = json.loads(output)
        return {
            "download_mbps": round((data.get("download") or 0) / 1_000_000, 2),
            "upload_mbps": round((data.get("upload") or 0) / 1_000_000, 2),
            "ping_ms": round(data.get("ping") or 0, 2),
            "jitter_ms": round(data.get("jitter") or 0, 2),
            "isp": data.get("client", {}).get("isp", "") if isinstance(data.get("client"), dict) else "",
            "server_id": str(data.get("server", {}).get("id", "")) if isinstance(data.get("server"), dict) else "",
            "server_name": data.get("server", {}).get("name", "") if isinstance(data.get("server"), dict) else "",
            "source": "speedtest-cli",
        }
    except (json.JSONDecodeError, ValueError):
        pass

    # Fallback: text parsing
    result = {"download_mbps": 0, "upload_mbps": 0, "ping_ms": 0, "jitter_ms": 0, "isp": "", "server_id": "", "server_name": "", "source": "speedtest-cli"}
    dl = re.search(rf"Download:\s*{_FLOAT_RE}\s*Mbit/s", output)
    if dl:
        result["download_mbps"] = float(dl.group(1))
    ul = re.search(rf"Upload:\s*{_FLOAT_RE}\s*Mbit/s", output)
    if ul:
        result["upload_mbps"] = float(ul.group(1))
    ping = re.search(rf"Ping:\s*{_FLOAT_RE}\s*ms", output)
    if ping:
        result["ping_ms"] = float(ping.group(1))
    return result


def _parse_ookla_speedtest(output: str) -> dict[str, Any]:
    """Parse Ookla 'speedtest' CLI text output."""
    result = {"download_mbps": 0, "upload_mbps": 0, "ping_ms": 0, "jitter_ms": 0, "isp": "", "server_id": "", "server_name": "", "source": "speedtest"}
    # Lines like: "Download: 123.45 Mbit/s"
    dl = re.search(rf"Download:\s*{_FLOAT_RE}\s*Mbit/s", output)
    if dl:
        result["download_mbps"] = float(dl.group(1))
    ul = re.search(rf"Upload:\s*{_FLOAT_RE}\s*Mbit/s", output)
    if ul:
        result["upload_mbps"] = float(ul.group(1))
    # Ookla format: "Ping: 12.34 ms   Jitter: 1.23 ms   ..."
    ping = re.search(rf"Ping:\s*{_FLOAT_RE}\s*ms", output)
    if ping:
        result["ping_ms"] = float(ping.group(1))
    jitter = re.search(rf"Jitter:\s*{_FLOAT_RE}\s*ms", output)
    if jitter:
        result["jitter_ms"] = float(jitter.group(1))
    # Server line: "Server: SomeServer (ID 12345) ..."
    server = re.search(r"Server:\s*(.+?)\s*\(ID\s*(\d+)\)", output)
    if server:
        result["server_name"] = server.group(1).strip()
        result["server_id"] = server.group(2)
    isp = re.search(r"ISP:\s*(.+)", output)
    if isp:
        result["isp"] = isp.group(1).strip()
    return result


@router.post("/speedtest/run")
async def run_speedtest() -> dict[str, Any]:
    """Run a speedtest via the installed CLI and store the result."""
    binary = _find_speedtest_binary()
    if not binary:
        return {
            "ok": False,
            "error": "Speedtest-CLI ist nicht installiert. Bitte 'speedtest-cli' (pip install speedtest-cli) oder das offizielle Ookla 'speedtest' Binary installieren.",
            "download_mbps": 0,
            "upload_mbps": 0,
            "ping_ms": 0,
        }

    # Build command: prefer --json for speedtest-cli; Ookla needs --accept-license
    is_ookla = binary.endswith("speedtest") and "speedtest-cli" not in binary
    if is_ookla:
        cmd = [binary, "--accept-license", "--accept-gdpr", "--format=human-readable"]
    else:
        cmd = [binary, "--json"]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        output = proc.stdout + "\n" + proc.stderr
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "Speedtest hat das Zeitlimit (120s) überschritten.", "download_mbps": 0, "upload_mbps": 0, "ping_ms": 0}
    except OSError as e:
        return {"ok": False, "error": f"Fehler beim Ausführen von Speedtest: {e}", "download_mbps": 0, "upload_mbps": 0, "ping_ms": 0}

    try:
        result = _parse_ookla_speedtest(output) if is_ookla else _parse_speedtest_cli(output)
    except Exception as e:
        return {"ok": False, "error": f"Parsen der Speedtest-Ausgabe fehlgeschlagen: {e}", "raw": output[:1000]}

    result["raw_output"] = output[:2000]
    result["ok"] = True

    # Persist
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await _ensure_schema(db)
        await db.execute(
            "INSERT INTO speedtest_results (timestamp, download_mbps, upload_mbps, ping_ms, jitter_ms, isp, server_id, server_name, raw_output, source) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                int(time.time()),
                result["download_mbps"],
                result["upload_mbps"],
                result["ping_ms"],
                result.get("jitter_ms", 0),
                result.get("isp", ""),
                result.get("server_id", ""),
                result.get("server_name", ""),
                result.get("raw_output", ""),
                result.get("source", "speedtest-cli"),
            ),
        )
        await db.commit()

    return result


@router.get("/speedtest/last")
async def last_speedtest() -> dict[str, Any]:
    """Return the last known speedtest result."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await _ensure_schema(db)
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT timestamp, download_mbps, upload_mbps, ping_ms, jitter_ms, isp, server_id, server_name, source "
            "FROM speedtest_results ORDER BY timestamp DESC LIMIT 1"
        ) as cur:
            row = await cur.fetchone()

    if not row:
        return {"available": False, "message": "Noch kein Speedtest durchgeführt."}

    return {
        "available": True,
        "timestamp": row["timestamp"],
        "time": time.strftime("%d.%m.%Y %H:%M:%S", time.localtime(row["timestamp"])),
        "download_mbps": row["download_mbps"],
        "upload_mbps": row["upload_mbps"],
        "ping_ms": row["ping_ms"],
        "jitter_ms": row["jitter_ms"],
        "isp": row["isp"],
        "server_id": row["server_id"],
        "server_name": row["server_name"],
        "source": row["source"],
    }


@router.get("/speedtest/history")
async def speedtest_history(limit: int = 100) -> list[dict[str, Any]]:
    """Return historical speedtest results."""
    limit = max(1, min(limit, 500))
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await _ensure_schema(db)
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT timestamp, download_mbps, upload_mbps, ping_ms, jitter_ms, isp, server_id, server_name, source "
            "FROM speedtest_results ORDER BY timestamp ASC LIMIT ?",
            (limit,),
        ) as cur:
            rows = await cur.fetchall()

    return [
        {
            "timestamp": r["timestamp"],
            "time": time.strftime("%d.%m.%Y %H:%M:%S", time.localtime(r["timestamp"])),
            "download_mbps": r["download_mbps"],
            "upload_mbps": r["upload_mbps"],
            "ping_ms": r["ping_ms"],
            "jitter_ms": r["jitter_ms"],
            "isp": r["isp"],
            "server_id": r["server_id"],
            "server_name": r["server_name"],
            "source": r["source"],
        }
        for r in rows
    ]