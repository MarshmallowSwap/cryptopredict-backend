from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
from app.core.supabase import get_supabase
from app.services.price_feed import get_asset_price
from app.services.yield_engine import compute_market_yield

router = APIRouter()

# ── HELPERS ──────────────────────────────────────────

def now_utc():
    return datetime.now(timezone.utc)

def parse_dt(s: str) -> datetime:
    """Parse ISO datetime string, always returns timezone-aware UTC."""
    s = s.replace("Z", "+00:00")
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt

def compute_yes_pct(yes_stake: float, no_stake: float) -> float:
    total = yes_stake + no_stake
    if total == 0:
        return 50.0
    return round((yes_stake / total) * 100, 2)

def compute_potential_payout(stake: float, side: bool, yes_stake: float, no_stake: float, fee: float = 0.02) -> float:
    pool_total = yes_stake + no_stake
    winner_pool = yes_stake if side else no_stake
    if winner_pool == 0:
        return stake * 2 * (1 - fee)
    ratio = pool_total / winner_pool
    return round(stake * ratio * (1 - fee), 6)

# ── SCHEMAS ──────────────────────────────────────────

class MarketCreate(BaseModel):
    title: str
    description: Optional[str] = None
    category: str = "crypto"  # crypto|defi|sport|politica|macro|tech|entertainment|scienza|nft|geopolitica|altro
    asset_symbol: Optional[str] = None
    resolution_type: str = "manual"
    resolution_rule: Optional[str] = None
    target_price: Optional[float] = None
    target_direction: Optional[str] = None
    expires_at: datetime
    creator_id: Optional[str] = None
    image_url: Optional[str] = None
    onchain_id: Optional[int] = None

class MarketImageUpdate(BaseModel):
    image_url: str

class BetPlace(BaseModel):
    user_id: str
    side: bool
    amount: float

# ── ENDPOINTS ────────────────────────────────────────

@router.get("")
async def list_markets(
    status: str = "open",
    category: Optional[str] = None,
    limit: int = Query(20, le=100),
    offset: int = 0
):
    sb = get_supabase()
    q = sb.table("markets").select("*").eq("status", status).order("created_at", desc=True)
    if category:
        q = q.eq("category", category)
    res = q.range(offset, offset + limit - 1).execute()
    markets = res.data or []

    for m in markets:
        expires = parse_dt(m["expires_at"])
        days_remaining = max(0, (expires - now_utc()).days)
        m["yield_info"] = compute_market_yield(
            pool_size=float(m.get("pool_size", 0)),
            days_remaining=days_remaining
        )
    return {"markets": markets, "total": len(markets)}


@router.get("/{market_id}")
async def get_market(market_id: str):
    sb = get_supabase()
    res = sb.table("markets").select("*").eq("id", market_id).single().execute()
    if not res.data:
        raise HTTPException(404, "Market not found")
    m = res.data
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
    sb = get_supabase()

    mkt = sb.table("markets").select("*").eq("id", market_id).single().execute().data
    if not mkt:
        raise HTTPException(404, "Market not found")
    if mkt["status"] != "open":
        raise HTTPException(400, f"Market is {mkt['status']}, not open")
    if parse_dt(mkt["expires_at"]) < now_utc():
        raise HTTPException(400, "Market has expired")

    user = sb.table("users").select("*").eq("id", body.user_id).single().execute().data
    if not user:
        raise HTTPException(404, "User not found")
    if float(user["usdc_balance"]) < body.amount:
        raise HTTPException(400, f"Insufficient balance")

    yes_stake = float(mkt["yes_stake"]) + (body.amount if body.side else 0)
    no_stake  = float(mkt["no_stake"])  + (body.amount if not body.side else 0)
    shares = body.amount / (yes_stake + no_stake) if (yes_stake + no_stake) > 0 else 0.5
    potential = compute_potential_payout(body.amount, body.side, yes_stake, no_stake)

    pos = sb.table("positions").insert({
        "user_id": body.user_id,
        "market_id": market_id,
        "side": body.side,
        "stake": body.amount,
        "shares": shares,
        "entry_pct": compute_yes_pct(yes_stake, no_stake) if body.side else 100 - compute_yes_pct(yes_stake, no_stake),
        "potential_payout": potential,
    }).execute().data[0]

    sb.table("markets").update({
        "pool_size": float(mkt["pool_size"]) + body.amount,
        "yes_stake": float(mkt["yes_stake"]) + (body.amount if body.side else 0),
        "no_stake":  float(mkt["no_stake"])  + (body.amount if not body.side else 0),
        "yes_pct": compute_yes_pct(yes_stake, no_stake),
        "no_pct":  100 - compute_yes_pct(yes_stake, no_stake),
        "participant_count": int(mkt["participant_count"]) + 1,
    }).eq("id", market_id).execute()

    sb.table("users").update({
        "usdc_balance": float(user["usdc_balance"]) - body.amount
    }).eq("id", body.user_id).execute()

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
    from app.core.config import settings
    if admin_token != settings.ADMIN_TOKEN:
        raise HTTPException(403, "Unauthorized")

    sb = get_supabase()
    mkt = sb.table("markets").select("*").eq("id", market_id).single().execute().data
    if not mkt:
        raise HTTPException(404, "Market not found")
    if mkt["status"] == "resolved":
        raise HTTPException(400, "Already resolved")

    sb.table("markets").update({
        "status": "resolved",
        "outcome": outcome,
        "resolved_at": now_utc().isoformat(),
    }).eq("id", market_id).execute()

    winning_side = outcome
    positions = sb.table("positions").select("*").eq("market_id", market_id).eq("side", winning_side).eq("status", "open").execute().data or []

    pool = float(mkt["pool_size"])
    yield_bonus = float(mkt.get("yield_accrued", 0)) * 0.50
    total_winning_stake = float(mkt["yes_stake"]) if winning_side else float(mkt["no_stake"])

    paid_out = 0
    for pos in positions:
        stake = float(pos["stake"])
        share = stake / total_winning_stake if total_winning_stake > 0 else 0
        payout = round((pool * share * 0.98) + (yield_bonus * share), 6)

        user = sb.table("users").select("usdc_balance, total_pnl, win_count").eq("id", pos["user_id"]).single().execute().data
        sb.table("users").update({
            "usdc_balance": float(user["usdc_balance"]) + payout,
            "total_pnl": float(user["total_pnl"]) + (payout - stake),
            "win_count": int(user["win_count"]) + 1,
        }).eq("id", pos["user_id"]).execute()

        sb.table("positions").update({
            "status": "won",
            "actual_payout": payout,
            "closed_at": now_utc().isoformat(),
        }).eq("id", pos["id"]).execute()

        sb.table("transactions").insert({
            "user_id": pos["user_id"],
            "type": "bet_win",
            "amount": payout,
            "market_id": market_id,
            "position_id": pos["id"],
            "description": f"Vincita mercato",
        }).execute()
        paid_out += payout

    sb.table("positions").update({
        "status": "lost",
        "actual_payout": 0,
        "closed_at": now_utc().isoformat(),
    }).eq("market_id", market_id).neq("side", winning_side).eq("status", "open").execute()

    return {
        "market_id": market_id,
        "outcome": "YES" if outcome else "NO",
        "winners": len(positions),
        "total_paid_out": paid_out,
    }

@router.patch("/{market_id}/image")
async def update_market_image(market_id: str, body: MarketImageUpdate):
    """Aggiorna l'image_url di un mercato."""
    sb = get_supabase()
    res = sb.table("markets").update({"image_url": body.image_url}).eq("id", market_id).execute()
    if not res.data:
        raise HTTPException(404, "Market not found")
    return {"ok": True, "image_url": body.image_url}

@router.get("/images/all")
async def get_all_images():
    """Restituisce {onchain_id: image_url} per tutti i mercati con immagine."""
    sb = get_supabase()
    res = sb.table("markets").select("onchain_id,image_url").not_.is_("image_url", "null").execute()
    result = {}
    for row in (res.data or []):
        if row.get("onchain_id") is not None:
            result[row["onchain_id"]] = row["image_url"]
    return result

@router.patch("/onchain/{onchain_id}/image")
async def update_market_image_by_onchain(onchain_id: int, body: MarketImageUpdate):
    """Aggiorna image_url per un mercato tramite il suo ID on-chain."""
    sb = get_supabase()
    # Cerca il mercato con quell'onchain_id
    res = sb.table("markets").select("id").eq("onchain_id", onchain_id).execute()
    if res.data:
        sb.table("markets").update({"image_url": body.image_url}).eq("onchain_id", onchain_id).execute()
    else:
        # Crea un record placeholder
        sb.table("markets").insert({
            "onchain_id": onchain_id,
            "image_url": body.image_url,
            "title": f"Market #{onchain_id}",
            "category": "crypto",
            "resolution_type": "manual",
            "expires_at": "2026-12-31T00:00:00+00:00",
            "status": "open"
        }).execute()
    return {"ok": True, "onchain_id": onchain_id, "image_url": body.image_url}
