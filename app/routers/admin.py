"""Operator-only reads during recovery. All legacy cron/cancel writes are quarantined."""
from collections import Counter
from fastapi import APIRouter, Depends
from app.core.recovery import require_recovery_admin
from app.core.supabase import get_supabase

router = APIRouter(dependencies=[Depends(require_recovery_admin)])


@router.get("/stats")
async def admin_stats():
    sb = get_supabase()
    markets = sb.table("markets").select("status", count="exact").execute()
    users = sb.table("users").select("id", count="exact").execute()
    positions = sb.table("positions").select("status, stake").execute()
    return {"total_users": users.count,
            "total_volume": round(sum(float(p["stake"]) for p in (positions.data or [])), 2),
            "markets_by_status": dict(Counter(m["status"] for m in (markets.data or []))),
            "accounting_basis": "legacy_unverified", "redeemable": False}


@router.get("/markets/pending")
async def pending_markets():
    sb = get_supabase()
    res = sb.table("markets").select("*").eq("status", "resolving").execute()
    return {"markets": res.data or [], "read_only": True}
