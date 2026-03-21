"""
Yield Engine — il meccanismo chiave di CryptoPredict.

Il capitale nei pool genera yield automatico (4.8% APY).
Alla risoluzione, il yield viene redistribuito:
  50% → boost payout vincitori
  30% → staker $CPRED
  20% → treasury protocollo
"""
from fastapi import APIRouter
from app.core.config import settings
from app.core.supabase import get_supabase
from datetime import datetime, date

router = APIRouter()

# ── CALCOLI ──────────────────────────────────────────

def compute_market_yield(pool_size: float, days_remaining: int) -> dict:
    """Calcola yield stimato per un mercato."""
    apy = settings.YIELD_APY
    daily_rate = apy / 365
    daily_yield = pool_size * daily_rate
    total_yield = daily_yield * max(days_remaining, 0)

    return {
        "apy": f"{apy * 100:.1f}%",
        "daily_yield": round(daily_yield, 4),
        "total_yield_estimated": round(total_yield, 4),
        "winner_bonus": round(total_yield * settings.YIELD_WINNER_SHARE, 4),
        "staker_share": round(total_yield * settings.YIELD_STAKER_SHARE, 4),
        "treasury_share": round(total_yield * settings.YIELD_TREASURY_SHARE, 4),
    }


def compute_position_yield_share(
    stake: float,
    pool_size: float,
    days_held: int
) -> float:
    """Calcola lo yield share accumulato per una singola posizione."""
    if pool_size == 0:
        return 0.0
    pool_share = stake / pool_size
    daily_rate = settings.YIELD_APY / 365
    position_yield = stake * daily_rate * days_held
    return round(position_yield, 6)


# ── CRON JOB: accrua yield giornaliero ───────────────

async def accrue_daily_yield():
    """
    Da chiamare ogni 24h via cron.
    Aggiorna yield_accrued per tutti i mercati aperti.
    """
    sb = get_supabase()
    markets = sb.table("markets").select("id, pool_size, yield_accrued").eq("status", "open").execute().data or []

    daily_rate = settings.YIELD_APY / 365
    today = date.today().isoformat()

    for m in markets:
        pool = float(m.get("pool_size", 0))
        current_yield = float(m.get("yield_accrued", 0))
        daily = pool * daily_rate

        new_yield = current_yield + daily
        daily_staker = daily * settings.YIELD_STAKER_SHARE

        # Aggiorna mercato
        sb.table("markets").update({
            "yield_accrued": new_yield,
            "yield_per_day": daily,
        }).eq("id", m["id"]).execute()

        # Snapshot giornaliero
        sb.table("yield_snapshots").insert({
            "market_id": m["id"],
            "pool_size": pool,
            "yield_generated": daily,
            "winner_share": round(daily * settings.YIELD_WINNER_SHARE, 6),
            "staker_share": round(daily * settings.YIELD_STAKER_SHARE, 6),
            "treasury_share": round(daily * settings.YIELD_TREASURY_SHARE, 6),
            "apy_applied": settings.YIELD_APY,
            "snapshot_date": today,
        }).execute()

        # Distribuisci staking rewards
        if daily_staker > 0:
            await distribute_staking_yield(sb, daily_staker)

    return {"accrued_markets": len(markets), "date": today}


async def distribute_staking_yield(sb, total_staker_yield: float):
    """Distribuisce lo yield agli staker CPRED proporzionalmente."""
    stakers = sb.table("staking_positions").select("id, user_id, amount").eq("is_active", True).execute().data or []
    total_staked = sum(float(s["amount"]) for s in stakers)
    if total_staked == 0:
        return

    for s in stakers:
        share = float(s["amount"]) / total_staked
        reward = round(total_staker_yield * share, 6)
        if reward <= 0:
            continue

        # Accredita reward
        sb.table("staking_positions").update({
            "rewards_earned": float(sb.table("staking_positions").select("rewards_earned").eq("id", s["id"]).single().execute().data.get("rewards_earned", 0)) + reward,
            "updated_at": datetime.utcnow().isoformat(),
        }).eq("id", s["id"]).execute()

        # Credita USDC all'utente
        user = sb.table("users").select("usdc_balance").eq("id", s["user_id"]).single().execute().data
        sb.table("users").update({
            "usdc_balance": float(user["usdc_balance"]) + reward
        }).eq("id", s["user_id"]).execute()

        # Transazione
        sb.table("transactions").insert({
            "user_id": s["user_id"],
            "type": "staking_reward",
            "amount": reward,
            "description": f"Staking yield giornaliero CPRED",
        }).execute()


# ── API ENDPOINTS ─────────────────────────────────────

@router.get("/stats")
async def yield_stats():
    """Statistiche globali dello yield."""
    sb = get_supabase()
    markets = sb.table("markets").select("pool_size, yield_accrued, expires_at").eq("status", "open").execute().data or []

    total_capital = sum(float(m.get("pool_size", 0)) for m in markets)
    total_yield_today = total_capital * (settings.YIELD_APY / 365)
    total_yield_accrued = sum(float(m.get("yield_accrued", 0)) for m in markets)

    return {
        "total_capital_locked": round(total_capital, 2),
        "yield_today": round(total_yield_today, 4),
        "total_yield_accrued": round(total_yield_accrued, 4),
        "apy": f"{settings.YIELD_APY * 100:.1f}%",
        "distribution": {
            "winners": f"{settings.YIELD_WINNER_SHARE * 100:.0f}%",
            "stakers": f"{settings.YIELD_STAKER_SHARE * 100:.0f}%",
            "treasury": f"{settings.YIELD_TREASURY_SHARE * 100:.0f}%",
        },
        "active_markets": len(markets),
    }


@router.get("/market/{market_id}")
async def market_yield(market_id: str):
    """Yield dettagliato per un mercato specifico."""
    sb = get_supabase()
    m = sb.table("markets").select("*").eq("id", market_id).single().execute().data
    if not m:
        raise HTTPException(404, "Market not found")

    expires = datetime.fromisoformat(m["expires_at"].replace("Z",""))
    days_remaining = max(0, (expires - datetime.utcnow()).days)

    return {
        "market_id": market_id,
        "pool_size": m["pool_size"],
        "yield_accrued": m.get("yield_accrued", 0),
        "yield_per_day": m.get("yield_per_day", 0),
        "days_remaining": days_remaining,
        **compute_market_yield(float(m["pool_size"]), days_remaining)
    }


@router.post("/accrue")
async def trigger_accrue(admin_token: str = ""):
    """Trigger manuale accrue (normalmente via cron)."""
    from app.core.config import settings as s
    from fastapi import HTTPException
    if admin_token != s.ADMIN_TOKEN:
        raise HTTPException(403, "Unauthorized")
    return await accrue_daily_yield()
