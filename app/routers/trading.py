from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta
import os
from supabase import create_client

router = APIRouter(prefix="/api/v1/trading", tags=["trading"])

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

class OrderCreate(BaseModel):
    market_id: int
    wallet: str
    side: bool          # True=YES False=NO
    order_type: str     # "limit" | "market"
    amount: float
    limit_price: Optional[float] = None  # 0-1 per limit
    currency: str = "ETH"
    expires_hours: int = 24

class OrderCancel(BaseModel):
    order_id: int
    wallet: str

@router.post("/orders")
async def create_order(order: OrderCreate):
    """Crea un nuovo ordine limite o market"""
    if order.order_type == "limit" and (order.limit_price is None or not 0 < order.limit_price < 1):
        raise HTTPException(400, "Limit price must be between 0 and 1")
    if order.amount <= 0:
        raise HTTPException(400, "Amount must be > 0")

    expires_at = (datetime.utcnow() + timedelta(hours=order.expires_hours)).isoformat()
    data = {
        "market_id":   order.market_id,
        "wallet":      order.wallet.lower(),
        "side":        order.side,
        "order_type":  order.order_type,
        "amount":      order.amount,
        "limit_price": order.limit_price,
        "currency":    order.currency,
        "status":      "open",
        "expires_at":  expires_at
    }
    result = supabase.table("trading_orders").insert(data).execute()
    return {"success": True, "order": result.data[0] if result.data else None}

@router.get("/orders/{market_id}")
async def get_orders(market_id: int, status: str = "open"):
    """Restituisce gli ordini per un mercato"""
    result = supabase.table("trading_orders") \
        .select("*") \
        .eq("market_id", market_id) \
        .eq("status", status) \
        .order("created_at", desc=True) \
        .limit(100) \
        .execute()
    return result.data or []

@router.get("/orders/user/{wallet}")
async def get_user_orders(wallet: str):
    """Ordini di un wallet specifico"""
    result = supabase.table("trading_orders") \
        .select("*") \
        .eq("wallet", wallet.lower()) \
        .order("created_at", desc=True) \
        .limit(50) \
        .execute()
    return result.data or []

@router.delete("/orders/{order_id}")
async def cancel_order(order_id: int, wallet: str):
    """Cancella un ordine aperto"""
    existing = supabase.table("trading_orders") \
        .select("*").eq("id", order_id).eq("wallet", wallet.lower()).execute()
    if not existing.data:
        raise HTTPException(404, "Order not found")
    if existing.data[0]["status"] != "open":
        raise HTTPException(400, "Order is not open")
    supabase.table("trading_orders") \
        .update({"status": "cancelled"}) \
        .eq("id", order_id).execute()
    return {"success": True}

@router.get("/orderbook/{market_id}")
async def get_orderbook(market_id: int):
    """Orderbook formattato: bid (YES) e ask (NO) separati"""
    result = supabase.table("trading_orders") \
        .select("*") \
        .eq("market_id", market_id) \
        .eq("status", "open") \
        .eq("order_type", "limit") \
        .gt("expires_at", datetime.utcnow().isoformat()) \
        .execute()

    orders = result.data or []
    bids = sorted([o for o in orders if o["side"]],  key=lambda x: x["limit_price"], reverse=True)
    asks = sorted([o for o in orders if not o["side"]], key=lambda x: x["limit_price"])

    # Aggrega per livello di prezzo
    def aggregate(orders_list):
        levels = {}
        for o in orders_list:
            p = round(float(o["limit_price"]), 3)
            if p not in levels:
                levels[p] = {"price": p, "amount": 0, "count": 0}
            levels[p]["amount"] += float(o["amount"])
            levels[p]["count"]  += 1
        return sorted(levels.values(), key=lambda x: x["price"], reverse=True)

    return {
        "bids": aggregate(bids)[:10],  # top 10 livelli YES
        "asks": aggregate(asks)[:10],  # top 10 livelli NO
        "spread": round(asks[0]["limit_price"] - bids[0]["limit_price"], 4) if bids and asks else None
    }
