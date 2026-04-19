from apscheduler.schedulers.asyncio import AsyncIOScheduler
from collectors import system_stats, interface_traffic, firewall_states, firewall_log, arp_hosts, netflow_clients
from database import purge_old_data

_scheduler: AsyncIOScheduler | None = None


def start_scheduler():
    global _scheduler
    _scheduler = AsyncIOScheduler(timezone="UTC")
    _scheduler.add_job(system_stats.collect,       "interval", seconds=60,   id="system",     misfire_grace_time=10)
    _scheduler.add_job(interface_traffic.collect,  "interval", seconds=30,   id="interfaces", misfire_grace_time=10)
    _scheduler.add_job(firewall_states.collect,    "interval", seconds=60,   id="fw_states",  misfire_grace_time=10)
    _scheduler.add_job(firewall_log.collect,       "interval", seconds=60,   id="fw_log",     misfire_grace_time=10)
    _scheduler.add_job(arp_hosts.collect,          "interval", seconds=120,  id="arp",        misfire_grace_time=20)
    _scheduler.add_job(netflow_clients.collect,    "interval", seconds=300,  id="netflow",    misfire_grace_time=30)
    _scheduler.add_job(purge_old_data,             "cron",     hour=3, minute=0, id="purge")
    _scheduler.start()
    print("[scheduler] started")


def stop_scheduler():
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
