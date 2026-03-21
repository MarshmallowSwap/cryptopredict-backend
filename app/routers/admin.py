"""
Admin router — risoluzione automatica mercati scaduti + cron jobs.
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks
from app.core.config import settings
from app.core.supabase import get_supabase
from app.services.price_feed import check_price_target
from app.services.yield_engine import accrue_daily_yield
from datetime import datetime

router = APIRouter()

def require_admin(token: str):
    if token != settings.ADMIN_TOKEN:
        raise HTTPException(403, "Unauthorized")

@router.get("/stats")
async def admin_stats(admin_token: str = ""):
    require_admin(admin_token)
    sb = get_supabase()
    markets = sb.table("markets").select("status", count="exact").execute()
    users = sb.table("users").select("id", count="exact").execute()
    positions = sb.table("positions").select("status, stake").execute()

    total_volume = sum(float(p["stake"]) for p in (positions.data or []))
    return {
        "total_users": users.count,
        "total_volume": round(total_volume, 2),
        "markets_by_status": {},
    }

@router.post("/cron/resolve-expired")
async def auto_resolve_expired(admin_token: str = "", background_tasks: BackgroundTasks = None):
    """Risolve automaticamente i mercati scaduti con target price."""
    require_admin(admin_token)
    sb = get_supabase()

    now = datetime.utcnow().isoformat()
    expired = sb.table("markets").select("*").eq("status", "open").eq("resolution_type", "price_target").lt("expires_at", now).execute().data or []

    resolved = []
    for mkt in expired:
        if not mkt.get("asset_symbol") or not mkt.get("target_price"):
            continue
        outcome = await check_price_target(
            asset_symbol=mkt["asset_symbol"],
            target_price=float(mkt["target_price"]),
            direction=mkt.get("target_direction", "above")
        )
        if outcome is None:
            continue

        # Risolvi
        from app.routers.markets import resolve_market
        result = await resolve_market(mkt["id"], outcome, settings.ADMIN_TOKEN)
        resolved.append({"market_id": mkt["id"], "outcome": outcome, **result})

    # Segna come "resolving" i mercati manuali scaduti
    manual_expired = sb.table("markets").select("id").eq("status", "open").eq("resolution_type", "manual").lt("expires_at", now).execute().data or []
    for m in manual_expired:
        sb.table("markets").update({"status": "resolving"}).eq("id", m["id"]).execute()

    return {
        "auto_resolved": len(resolved),
        "awaiting_manual": len(manual_expired),
        "resolved": resolved,
    }

@router.post("/cron/accrue-yield")
async def cron_accrue_yield(admin_token: str = ""):
    """Accrua yield giornaliero su tutti i mercati aperti."""
    require_admin(admin_token)
    return await accrue_daily_yield()

@router.post("/cron/leaderboard")
async def update_leaderboard(admin_token: str = ""):
    """Aggiorna ranking settimanale."""
    require_admin(admin_token)
    sb = get_supabase()
    users = sb.table("users").select("id, win_count, loss_count, total_pnl").order("total_pnl", desc=True).limit(100).execute().data or []
    return {"leaderboard_size": len(users), "top_3": users[:3]}

@router.get("/markets/pending")
async def pending_markets(admin_token: str = ""):
    """Mercati in attesa di risoluzione manuale."""
    require_admin(admin_token)
    sb = get_supabase()
    res = sb.table("markets").select("*").eq("status", "resolving").execute()
    return {"markets": res.data or []}

@router.post("/markets/{market_id}/cancel")
async def cancel_market(market_id: str, admin_token: str = ""):
    """Cancella un mercato e rimborsa tutti."""
    require_admin(admin_token)
    sb = get_supabase()
    mkt = sb.table("markets").select("*").eq("id", market_id).single().execute().data
    if not mkt:
        raise HTTPException(404, "Market not found")

    positions = sb.table("positions").select("*").eq("market_id", market_id).eq("status", "open").execute().data or []
    refunded = 0
    for pos in positions:
        stake = float(pos["stake"])
        user = sb.table("users").select("usdc_balance").eq("id", pos["user_id"]).single().execute().data
        sb.table("users").update({"usdc_balance": float(user["usdc_balance"]) + stake}).eq("id", pos["user_id"]).execute()
        sb.table("positions").update({"status": "refunded", "actual_payout": stake}).eq("id", pos["id"]).execute()
        sb.table("transactions").insert({
            "user_id": pos["user_id"],
            "type": "bet_refund",
            "amount": stake,
            "market_id": market_id,
            "position_id": pos["id"],
            "description": "Rimborso mercato cancellato",
        }).execute()
        refunded += stake

    sb.table("markets").update({"status": "cancelled"}).eq("id", market_id).execute()
    return {"cancelled": True, "positions_refunded": len(positions), "total_refunded": refunded}
