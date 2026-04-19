from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import asyncio

from database import init_db
from scheduler import start_scheduler, stop_scheduler
from collectors import system_stats, interface_traffic, firewall_states, arp_hosts
from collectors.opnsense_client import close_client
from routers import system, interfaces, clients, firewall, hosts, gateways, dns, wan, traffic


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    start_scheduler()
    # warm-up: collect immediately so dashboard has data on first load
    await asyncio.gather(
        system_stats.collect(),
        interface_traffic.collect(),
        firewall_states.collect(),
        arp_hosts.collect(),
        return_exceptions=True,
    )
    yield
    stop_scheduler()
    await close_client()


app = FastAPI(title="Homelab Dashboard", lifespan=lifespan)

app.include_router(system.router,     prefix="/api")
app.include_router(interfaces.router, prefix="/api")
app.include_router(clients.router,    prefix="/api")
app.include_router(firewall.router,   prefix="/api")
app.include_router(hosts.router,      prefix="/api")
app.include_router(gateways.router,   prefix="/api")
app.include_router(dns.router,        prefix="/api")
app.include_router(wan.router,        prefix="/api")
app.include_router(traffic.router,    prefix="/api")

app.mount("/", StaticFiles(directory="../frontend", html=True), name="frontend")
