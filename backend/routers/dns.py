from fastapi import APIRouter
from collectors.opnsense_client import api_get

router = APIRouter()


@router.get("/dns/stats")
async def get_dns_stats():
    try:
        data = await api_get("unbound/diagnostics/stats")
        inner = data.get("data", {})
        total = inner.get("total", {}).get("num", {})
        rec_time = inner.get("total", {}).get("recursion", {}).get("time", {})
        uptime = inner.get("time", {})

        queries = int(total.get("queries", 0))
        cachehits = int(total.get("cachehits", 0))
        cachemiss = int(total.get("cachemiss", 0))
        cache_pct = round(cachehits / queries * 100, 1) if queries else 0
        avg_ms = round(float(rec_time.get("avg", 0)) * 1000, 1)
        up_sec = float(uptime.get("up", 0))

        return {
            "queries": queries,
            "cachehits": cachehits,
            "cachemiss": cachemiss,
            "cache_pct": cache_pct,
            "avg_recursion_ms": avg_ms,
            "uptime_sec": up_sec,
        }
    except Exception as e:
        return {"error": str(e)}


@router.get("/dns/top")
async def get_dns_top():
    try:
        data = await api_get("unbound/overview/searchQueries")
        rows = data.get("rows", [])
        return rows[:20]
    except Exception:
        return []
