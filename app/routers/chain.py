from fastapi import APIRouter, Query
from app.core.supabase import get_supabase
from app.core.config import settings

router = APIRouter()

CHAIN_ID = 84532


@router.get("/status")
async def chain_index_status():
    sb = get_supabase()
    state = (
        sb.table("recovery_indexer_state")
        .select("*")
        .eq("chain_id", CHAIN_ID)
        .eq("contract_address", settings.PREDICTION_MARKET_ADDRESS.lower())
        .limit(1)
        .execute()
    ).data or []
    count = (
        sb.table("recovery_chain_events")
        .select("id", count="exact")
        .eq("chain_id", CHAIN_ID)
        .eq("contract_address", settings.PREDICTION_MARKET_ADDRESS.lower())
        .eq("canonical", True)
        .limit(1)
        .execute()
    )
    return {
        "chain_id": CHAIN_ID,
        "contract_address": settings.PREDICTION_MARKET_ADDRESS,
        "events_indexed": count.count or 0,
        "state": state[0] if state else None,
        "source_of_truth": "blockchain",
        "database_role": "index_only",
    }


@router.get("/events")
async def chain_events(
    market_id: int | None = Query(default=None, ge=0),
    event_name: str | None = Query(default=None, min_length=1, max_length=64),
    limit: int = Query(default=100, ge=1, le=500),
):
    sb = get_supabase()
    q = (
        sb.table("recovery_chain_events")
        .select("*")
        .eq("chain_id", CHAIN_ID)
        .eq("contract_address", settings.PREDICTION_MARKET_ADDRESS.lower())
        .eq("canonical", True)
        .order("block_number", desc=True)
        .order("log_index", desc=True)
        .limit(limit)
    )
    if market_id is not None:
        q = q.eq("market_id", str(market_id))
    if event_name:
        q = q.eq("event_name", event_name)
    rows = q.execute().data or []
    return {
        "events": rows,
        "total_returned": len(rows),
        "source_of_truth": "blockchain",
        "database_role": "index_only",
    }
