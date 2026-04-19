import httpx
import warnings
from config import OPNSENSE_HOST, OPNSENSE_API_KEY, OPNSENSE_API_SECRET

warnings.filterwarnings("ignore", message=".*SSL.*")
warnings.filterwarnings("ignore", message=".*certificate.*")

_client: httpx.AsyncClient | None = None


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            base_url=f"https://{OPNSENSE_HOST}",
            auth=(OPNSENSE_API_KEY, OPNSENSE_API_SECRET),
            verify=False,
            timeout=15.0,
        )
    return _client


async def api_get(path: str) -> dict:
    r = await get_client().get(f"/api/{path}")
    r.raise_for_status()
    return r.json()


async def api_post(path: str, data: dict | None = None) -> dict:
    r = await get_client().post(f"/api/{path}", json=data or {})
    r.raise_for_status()
    return r.json()


async def close_client():
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()
    _client = None
