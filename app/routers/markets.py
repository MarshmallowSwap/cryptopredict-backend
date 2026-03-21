from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from app.core.supabase import get_supabase
from app.services.price_feed import get_asset_price
from app.services.yield_engine import compute_market_yield
import math

router = APIRouter()

# ── SCHEMAS ──────────────────────────────────────────

class MarketCreate(BaseModel):
    title: str
    description: Optional[str] = None
    category: str = "crypto"
    asset_symbol: Optional[str] = None
    resolution_type: str = "manual"
    resolution_rule: Optional[str] = None
    target_price: Optional[float] = None
    target_direction: Optional[str] = None  # 'above' | 'below'
    expires_at: datetime
    creator_id: Optional[str] = None

class BetPlace(BaseModel):
    user_id: str
    side: bool   # True=YES, False=NO
    amount: float  # USDC

# ── HELPERS ──────────────────────────────────────────

def compute_yes_pct(yes_stake: float, no_stake: float) -> float:
    total = yes_stake + no_stake
    if total == 0:
        return 50.0
    return round((yes_stake / total) * 100, 2)

def compute_potential_payout(stake: float, side: bool, yes_stake: float, no_stake: float, fee: float = 0.02) -> float:
    """LMSR-style simplified: payout proporzionale alla quota del pool vincente."""
    pool_total = yes_stake + no_stake
    winner_pool = yes_stake if side else no_stake
    if winner_pool == 0:
        return stake * 2 * (1 - fee)
    ratio = pool_total / winner_pool
    return round(stake * ratio * (1 - fee), 6)

# ── ENDPOINTS ────────────────────────────────────────

@router.get("")
async def list_markets(
    status: str = "open",
    category: Optional[str] = None,
    limit: int = Query(20, le=100),
    offset: int = 0
):
    """Lista mercati attivi con yield calcolato."""
    sb = get_supabase()
    q = sb.table("markets").select("*").eq("status", status).order("created_at", desc=True)
    if category:
        q = q.eq("category", category)
    res = q.range(offset, offset + limit - 1).execute()
    markets = res.data or []

    # Aggiungi yield per ogni mercato
    for m in markets:
        m["yield_info"] = compute_market_yield(
            pool_size=float(m.get("pool_size", 0)),
            days_remaining=max(0, (datetime.fromisoformat(m["expires_at"].replace("Z","")) - datetime.utcnow()).days)
        )
    return {"markets": markets, "total": len(markets)}


@router.get("/{market_id}")
async def get_market(market_id: str):
    sb = get_supabase()
    res = sb.table("markets").select("*").eq("id", market_id).single().execute()
    if not res.data:
        raise HTTPException(404, "Market not found")
    m = res.data
    # Aggiungi prezzo live se mercato crypto
    if m.get("asset_symbol"):
        try:
            m["current_price"] = await get_asset_price(m["asset_symbol"])
        except Exception:
            m["current_price"] = None
    return m


@router.post("")
async def create_market(body: MarketCreate):
    sb = get_supabase()
    data = body.dict()
    data["expires_at"] = data["expires_at"].isoformat()
    res = sb.table("markets").insert(data).execute()
    if not res.data:
        raise HTTPException(500, "Failed to create market")
    return res.data[0]


@router.post("/{market_id}/bet")
async def place_bet(market_id: str, body: BetPlace):
    """Piazza una scommessa YES o NO su un mercato."""
    sb = get_supabase()

    # 1. Fetch market
    mkt = sb.table("markets").select("*").eq("id", market_id).single().execute().data
    if not mkt:
        raise HTTPException(404, "Market not found")
    if mkt["status"] != "open":
        raise HTTPException(400, f"Market is {mkt['status']}, not open")
    if datetime.fromisoformat(mkt["expires_at"].replace("Z","")) < datetime.utcnow():
        raise HTTPException(400, "Market has expired")

    # 2. Fetch user & check balance
    user = sb.table("users").select("*").eq("id", body.user_id).single().execute().data
    if not user:
        raise HTTPException(404, "User not found")
    if float(user["usdc_balance"]) < body.amount:
        raise HTTPException(400, f"Insufficient balance: have {user['usdc_balance']} USDC, need {body.amount}")

    # 3. Calcola shares e payout potenziale
    yes_stake = float(mkt["yes_stake"]) + (body.amount if body.side else 0)
    no_stake  = float(mkt["no_stake"])  + (body.amount if not body.side else 0)
    shares = body.amount / (yes_stake + no_stake) if (yes_stake + no_stake) > 0 else 0.5
    potential = compute_potential_payout(body.amount, body.side, yes_stake, no_stake)

    # 4. Crea posizione
    pos = sb.table("positions").insert({
        "user_id": body.user_id,
        "market_id": market_id,
        "side": body.side,
        "stake": body.amount,
        "shares": shares,
        "entry_pct": compute_yes_pct(yes_stake, no_stake) if body.side else 100 - compute_yes_pct(yes_stake, no_stake),
        "potential_payout": potential,
    }).execute().data[0]

    # 5. Aggiorna mercato
    sb.table("markets").update({
        "pool_size": float(mkt["pool_size"]) + body.amount,
        "yes_stake": float(mkt["yes_stake"]) + (body.amount if body.side else 0),
        "no_stake": float(mkt["no_stake"]) + (body.amount if not body.side else 0),
        "yes_pct": compute_yes_pct(yes_stake, no_stake),
        "no_pct": 100 - compute_yes_pct(yes_stake, no_stake),
        "participant_count": int(mkt["participant_count"]) + 1,
    }).eq("id", market_id).execute()

    # 6. Scala balance utente
    sb.table("users").update({
        "usdc_balance": float(user["usdc_balance"]) - body.amount
    }).eq("id", body.user_id).execute()

    # 7. Registra transazione
    sb.table("transactions").insert({
        "user_id": body.user_id,
        "type": "bet_place",
        "amount": -body.amount,
        "market_id": market_id,
        "position_id": pos["id"],
        "description": f"Scommessa {'YES' if body.side else 'NO'} su mercato",
    }).execute()

    return {
        "position_id": pos["id"],
        "stake": body.amount,
        "side": "YES" if body.side else "NO",
        "potential_payout": potential,
        "shares": shares,
    }


@router.post("/{market_id}/resolve")
async def resolve_market(market_id: str, outcome: bool, admin_token: str = ""):
    """Risolve un mercato e paga i vincitori."""
    from app.core.config import settings
    if admin_token != settings.ADMIN_TOKEN:
        raise HTTPException(403, "Unauthorized")

    sb = get_supabase()
    mkt = sb.table("markets").select("*").eq("id", market_id).single().execute().data
    if not mkt:
        raise HTTPException(404, "Market not found")
    if mkt["status"] == "resolved":
        raise HTTPException(400, "Already resolved")

    # Aggiorna status mercato
    sb.table("markets").update({
        "status": "resolved",
        "outcome": outcome,
        "resolved_at": datetime.utcnow().isoformat(),
    }).eq("id", market_id).execute()

    # Fetch posizioni vincenti
    winning_side = outcome  # True=YES, False=NO
    positions = sb.table("positions").select("*").eq("market_id", market_id).eq("side", winning_side).eq("status", "open").execute().data or []

    pool = float(mkt["pool_size"])
    yield_bonus = float(mkt.get("yield_accrued", 0)) * 0.50  # 50% del yield ai vincitori
    total_winning_stake = float(mkt["yes_stake"]) if winning_side else float(mkt["no_stake"])

    paid_out = 0
    for pos in positions:
        stake = float(pos["stake"])
        share = stake / total_winning_stake if total_winning_stake > 0 else 0
        payout = round((pool * share * 0.98) + (yield_bonus * share), 6)  # 2% platform fee

        # Paga utente
        user = sb.table("users").select("usdc_balance, total_pnl, win_count").eq("id", pos["user_id"]).single().execute().data
        sb.table("users").update({
            "usdc_balance": float(user["usdc_balance"]) + payout,
            "total_pnl": float(user["total_pnl"]) + (payout - stake),
            "win_count": int(user["win_count"]) + 1,
        }).eq("id", pos["user_id"]).execute()

        # Aggiorna posizione
        sb.table("positions").update({
            "status": "won",
            "actual_payout": payout,
            "closed_at": datetime.utcnow().isoformat(),
        }).eq("id", pos["id"]).execute()

        # Transazione
        sb.table("transactions").insert({
            "user_id": pos["user_id"],
            "type": "bet_win",
            "amount": payout,
            "market_id": market_id,
            "position_id": pos["id"],
            "description": f"Vincita mercato · payout {payout:.2f} USDC",
        }).execute()
        paid_out += payout

    # Aggiorna posizioni perdenti
    sb.table("positions").update({
        "status": "lost",
        "actual_payout": 0,
        "closed_at": datetime.utcnow().isoformat(),
    }).eq("market_id", market_id).neq("side", winning_side).eq("status", "open").execute()

    # Aggiorna loss_count per i perdenti
    losing_positions = sb.table("positions").select("user_id").eq("market_id", market_id).eq("side", not winning_side).execute().data or []
    for lp in losing_positions:
        u = sb.table("users").select("loss_count, total_pnl").eq("id", lp["user_id"]).single().execute().data
        sb.table("users").update({
            "loss_count": int(u["loss_count"]) + 1,
        }).eq("id", lp["user_id"]).execute()

    return {
        "market_id": market_id,
        "outcome": "YES" if outcome else "NO",
        "winners": len(positions),
        "total_paid_out": paid_out,
    }
