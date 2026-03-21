#!/usr/bin/env python3
"""
Avvia il server FastAPI + scheduler cron:
  - Yield giornaliero (ogni 24h alle 00:05)
  - Auto-resolve mercati scaduti (ogni 5 min)
    → crypto/macro/defi: prezzo Binance/CoinGecko → on-chain
    → sport/politica/altro: log + notifica admin panel
"""
import uvicorn
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from app.main import app
from app.services.yield_engine import accrue_daily_yield
from app.services.auto_resolver import run_auto_resolver
from app.core.config import settings

scheduler = AsyncIOScheduler()

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
        run_auto_resolver,
        IntervalTrigger(minutes=5),
        id="auto_resolve",
        replace_existing=True,
        max_instances=1,       # evita sovrapposizioni
        coalesce=True,         # salta run mancati se server era offline
    )
    scheduler.start()
    print("✅ Scheduler avviato:")
    print("   - yield accrual: ogni giorno 00:05")
    print("   - auto-resolve:  ogni 5 minuti")
    print("   - admin panel:   https://cryptopredict-chi.vercel.app/admin.html")

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
