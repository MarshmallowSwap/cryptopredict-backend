#!/usr/bin/env python3
"""
Avvia il server FastAPI + scheduler cron per:
  - Accrue yield giornaliero (ogni 24h alle 00:05)
  - Auto-resolve mercati scaduti (ogni 5 minuti)
"""
import uvicorn
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from app.main import app
from app.services.yield_engine import accrue_daily_yield
from app.core.config import settings
import asyncio

scheduler = AsyncIOScheduler()

async def auto_resolve_job():
    """Chiama l'endpoint di auto-resolve ogni 5 min."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            await client.post(
                "http://localhost:8000/api/v1/admin/cron/resolve-expired",
                params={"admin_token": settings.ADMIN_TOKEN}
            )
    except Exception as e:
        print(f"[CRON] Auto-resolve error: {e}")

@app.on_event("startup")
async def startup():
    # Yield accrual: ogni giorno alle 00:05
    scheduler.add_job(
        accrue_daily_yield,
        CronTrigger(hour=0, minute=5),
        id="daily_yield",
        replace_existing=True,
    )
    # Auto-resolve: ogni 5 minuti
    scheduler.add_job(
        auto_resolve_job,
        IntervalTrigger(minutes=5),
        id="auto_resolve",
        replace_existing=True,
    )
    scheduler.start()
    print("✅ Scheduler avviato: yield@00:05, auto-resolve ogni 5min")

@app.on_event("shutdown")
async def shutdown():
    scheduler.shutdown()

if __name__ == "__main__":
    uvicorn.run(
        "start:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        workers=1,
    )
