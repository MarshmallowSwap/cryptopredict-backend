from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from app.core.supabase import get_supabase

router = APIRouter()

class UserCreate(BaseModel):
    telegram_id: Optional[int] = None
    username: Optional[str] = None
    display_name: Optional[str] = None

class UserDeposit(BaseModel):
    user_id: str
    amount: float
    currency: str = "USDC"
    nowpayments_id: Optional[str] = None

@router.get("/{user_id}")
async def get_user(user_id: str):
    sb = get_supabase()
    res = sb.table("users").select("*").eq("id", user_id).single().execute()
    if not res.data:
        raise HTTPException(404, "User not found")
    return res.data

@router.get("/telegram/{telegram_id}")
async def get_user_by_telegram(telegram_id: int):
    sb = get_supabase()
    res = sb.table("users").select("*").eq("telegram_id", telegram_id).single().execute()
    if not res.data:
        raise HTTPException(404, "User not found")
    return res.data

@router.post("")
async def create_user(body: UserCreate):
    sb = get_supabase()
    # Controlla se esiste già
    if body.telegram_id:
        existing = sb.table("users").select("id").eq("telegram_id", body.telegram_id).execute()
        if existing.data:
            return existing.data[0]
    res = sb.table("users").insert(body.dict(exclude_none=True)).execute()
    if not res.data:
        raise HTTPException(500, "Failed to create user")
    return res.data[0]

@router.get("/{user_id}/positions")
async def get_user_positions(user_id: str, status: Optional[str] = None):
    sb = get_supabase()
    q = sb.table("positions").select("*, markets(title, expires_at, status, outcome)").eq("user_id", user_id)
    if status:
        q = q.eq("status", status)
    res = q.order("created_at", desc=True).execute()
    return {"positions": res.data or []}

@router.get("/{user_id}/transactions")
async def get_user_transactions(user_id: str, limit: int = 20):
    sb = get_supabase()
    res = sb.table("transactions").select("*").eq("user_id", user_id).order("created_at", desc=True).limit(limit).execute()
    return {"transactions": res.data or []}

@router.get("/{user_id}/stats")
async def get_user_stats(user_id: str):
    sb = get_supabase()
    user = sb.table("users").select("*").eq("id", user_id).single().execute().data
    if not user:
        raise HTTPException(404, "User not found")

    # Posizioni aperte con yield
    open_positions = sb.table("positions").select("stake, market_id, created_at").eq("user_id", user_id).eq("status", "open").execute().data or []

    from datetime import datetime
    from app.services.yield_engine import compute_position_yield_share

    total_yield_share = 0
    for pos in open_positions:
        days = (datetime.utcnow() - datetime.fromisoformat(pos["created_at"].replace("Z",""))).days
        # Fetch pool size
        mkt = sb.table("markets").select("pool_size").eq("id", pos["market_id"]).single().execute().data
        if mkt:
            total_yield_share += compute_position_yield_share(
                stake=float(pos["stake"]),
                pool_size=float(mkt.get("pool_size", 0)),
                days_held=days
            )

    # Staking
    staking = sb.table("staking_positions").select("amount, rewards_earned, pool, apy").eq("user_id", user_id).eq("is_active", True).execute().data or []

    return {
        "user_id": user_id,
        "usdc_balance": user["usdc_balance"],
        "cpred_balance": user["cpred_balance"],
        "cpred_staked": user["cpred_staked"],
        "total_pnl": user["total_pnl"],
        "win_count": user["win_count"],
        "loss_count": user["loss_count"],
        "win_rate": round(user["win_count"] / max(user["win_count"] + user["loss_count"], 1) * 100, 1),
        "open_positions": len(open_positions),
        "yield_share_accumulated": round(total_yield_share, 4),
        "staking": staking,
    }


@router.get("/wallet/{wallet_address}")
async def get_user_by_wallet(wallet_address: str):
    """Cerca utente per wallet address (case-insensitive)."""
    sb = get_supabase()
    # Prova lowercase
    res = sb.table("users").select("*").ilike("wallet_address", wallet_address).execute()
    if res.data:
        return res.data[0]
    raise HTTPException(404, "User not found")

@router.post("/{user_id}/deposit")
async def deposit(user_id: str, body: UserDeposit):
    """Simula un deposito (in produzione: webhook NOWPayments)."""
    sb = get_supabase()
    user = sb.table("users").select("usdc_balance").eq("id", user_id).single().execute().data
    if not user:
        raise HTTPException(404, "User not found")

    sb.table("users").update({
        "usdc_balance": float(user["usdc_balance"]) + body.amount
    }).eq("id", user_id).execute()

    sb.table("transactions").insert({
        "user_id": user_id,
        "type": "deposit",
        "amount": body.amount,
        "currency": body.currency,
        "description": f"Deposito {body.amount} {body.currency}",
        "metadata": {"nowpayments_id": body.nowpayments_id} if body.nowpayments_id else {}
    }).execute()

    return {"success": True, "new_balance": float(user["usdc_balance"]) + body.amount}
