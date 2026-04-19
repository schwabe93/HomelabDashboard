from fastapi import APIRouter
from collectors.opnsense_client import api_get

router = APIRouter()


@router.get("/gateways")
async def get_gateways():
    try:
        data = await api_get("routes/gateway/status")
        items = data.get("items", [])
        return [
            {
                "name": gw.get("name", ""),
                "address": gw.get("address", ""),
                "monitor": gw.get("monitor", ""),
                "status": gw.get("status_translated", "Unknown"),
                "online": gw.get("status_translated", "").lower() == "online",
                "loss": gw.get("loss", "—"),
                "delay": gw.get("delay", "—"),
                "stddev": gw.get("stddev", "—"),
            }
            for gw in items
        ]
    except Exception as e:
        return []
