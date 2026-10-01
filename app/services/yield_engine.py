"""Legacy yield estimates for display, never realized or redeemable income.

No strategy funding was verified. Accrual and reward mutations are quarantined.
"""
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from app.core.config import settings
from app.core.supabase import get_supabase
from app.core.recovery import block_legacy_write

router = APIRouter()
SIMULATION = {"accounting_basis": "legacy_simulation", "redeemable": False,
              "funding_verified": False}


def compute_market_yield(pool_size: float, days_remaining: int) -> dict:
    apy = settings.YIELD_APY
    daily_yield = pool_size * apy / 365
    total_yield = daily_yield * max(days_remaining, 0)
    return {"apy": f"{apy * 100:.1f}%", "daily_yield": round(daily_yield, 4),
            "total_yield_estimated": round(total_yield, 4),
            "winner_bonus": round(total_yield * settings.YIELD_WINNER_SHARE, 4),
            "staker_share": round(total_yield * settings.YIELD_STAKER_SHARE, 4),
            "treasury_share": round(total_yield * settings.YIELD_TREASURY_SHARE, 4),
            **SIMULATION}


def compute_position_yield_share(stake: float, pool_size: float, days_held: int) -> float:
    if pool_size == 0:
        return 0.0
    return round(stake * settings.YIELD_APY / 365 * max(days_held, 0), 6)


async def accrue_daily_yield():
    block_legacy_write("unfunded legacy yield accrual")


async def distribute_staking_yield(sb, total_staker_yield: float):
    block_legacy_write("unfunded legacy staking rewards")


@router.get("/stats")
async def yield_stats():
    sb = get_supabase()
    markets = sb.table("markets").select("pool_size, yield_accrued, expires_at").eq("status", "open").execute().data or []
    total_capital = sum(float(m.get("pool_size", 0)) for m in markets)
    return {"total_capital_locked": round(total_capital, 2),
            "yield_today": round(total_capital * settings.YIELD_APY / 365, 4),
            "total_yield_accrued": round(sum(float(m.get("yield_accrued", 0)) for m in markets), 4),
            "apy": f"{settings.YIELD_APY * 100:.1f}%",
            "distribution": {"winners": f"{settings.YIELD_WINNER_SHARE * 100:.0f}%",
                             "stakers": f"{settings.YIELD_STAKER_SHARE * 100:.0f}%",
                             "treasury": f"{settings.YIELD_TREASURY_SHARE * 100:.0f}%"},
            "active_markets": len(markets), **SIMULATION}


@router.get("/market/{market_id}")
async def market_yield(market_id: str):
    sb = get_supabase()
    m = sb.table("markets").select("*").eq("id", market_id).single().execute().data
    if not m:
        raise HTTPException(404, "Market not found")
    expires = datetime.fromisoformat(m["expires_at"].replace("Z", "+00:00"))
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    days_remaining = max(0, (expires - datetime.now(timezone.utc)).days)
    return {"market_id": market_id, "pool_size": m["pool_size"],
            "yield_accrued": m.get("yield_accrued", 0), "yield_per_day": m.get("yield_per_day", 0),
            "days_remaining": days_remaining,
            **compute_market_yield(float(m["pool_size"]), days_remaining)}


@router.post("/accrue")
async def trigger_accrue():
    # Defense in depth for direct calls; HTTP mutations are already blocked.
    raise HTTPException(503, "Unfunded yield accrual is disabled during recovery")
