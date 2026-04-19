from fastapi import APIRouter
from collectors.opnsense_client import api_get

router = APIRouter()

_WAN_IDENTIFIERS = {"wan", "opt2"}   # WAN (PPPoE) + STARLINK


@router.get("/wan")
async def get_wan():
    try:
        data = await api_get("interfaces/overview/interfacesInfo")
        rows = data.get("rows", [])
        result = []
        for iface in rows:
            ident = iface.get("identifier", "")
            if ident not in _WAN_IDENTIFIERS:
                continue
            stats = iface.get("statistics", {})
            result.append({
                "identifier": ident,
                "name": iface.get("description", ident.upper()),
                "addr4": iface.get("addr4", "").split("/")[0],
                "status": iface.get("status", ""),
                "link_type": iface.get("link_type", ""),
                "input_errors": int(stats.get("input errors", 0)),
                "output_errors": int(stats.get("output errors", 0)),
                "queue_drops": int(stats.get("input queue drops", 0)),
            })
        return result
    except Exception as e:
        return []


@router.get("/interfaces/errors")
async def get_interface_errors():
    try:
        data = await api_get("interfaces/overview/interfacesInfo")
        rows = data.get("rows", [])
        result = []
        for iface in rows:
            if not iface.get("is_physical"):
                continue
            stats = iface.get("statistics", {})
            in_err = int(stats.get("input errors", 0))
            out_err = int(stats.get("output errors", 0))
            drops = int(stats.get("input queue drops", 0))
            result.append({
                "device": stats.get("device", ""),
                "name": iface.get("description", ""),
                "input_errors": in_err,
                "output_errors": out_err,
                "queue_drops": drops,
                "total_errors": in_err + out_err + drops,
            })
        return result
    except Exception as e:
        return []
