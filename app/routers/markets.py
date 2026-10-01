"""Original markets API, now backed only by the verified recovery contract.

The former DB balance mutation handlers are preserved as an unimportable
legacy source snapshot. No endpoint in this router signs or writes anything.
The canonical alias uses the same Catalog instance, not a second backend.
"""
from __future__ import annotations

import re
import threading
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request

from app.core.config import settings
from app.services.chain_catalog import Catalog, ReadError, MARKET, DEPLOY_TX, TOKENS, ZERO

router = APIRouter()
canonical_router = APIRouter()
_catalog = Catalog()
_slots = threading.BoundedSemaphore(4)


def validate_request(request: Request, allowed: set[str]) -> None:
    keys = list(request.query_params.keys())
    if any(k not in allowed or len(request.query_params.getlist(k)) != 1 for k in keys):
        raise HTTPException(400, detail={"code": "UNSUPPORTED_QUERY"})


def read_snapshot() -> dict:
    expected = {
        "PREDICTION_MARKET_ADDRESS": MARKET,
        "RECOVERY_DEPLOYMENT_TX_HASH": DEPLOY_TX,
        "CPRED_TOKEN_ADDRESS": TOKENS[3],
        "MOCK_USDC_ADDRESS": TOKENS[1],
        "MOCK_USDT_ADDRESS": TOKENS[2],
        "POSITION_MARKET_ADDRESS": ZERO,
        "AMM_POOL_ADDRESS": ZERO,
        "PRESALE_STAKING_ADDRESS": ZERO,
    }
    if any(str(getattr(settings, k, "")).lower() != v for k, v in expected.items()):
        raise HTTPException(503, detail={"code": "RECOVERY_CONFIG_MISMATCH"})
    if not _slots.acquire(blocking=False):
        raise HTTPException(503, detail={"code": "CATALOG_BUSY"})
    try:
        return _catalog.snapshot()
    except ReadError as exc:
        raise HTTPException(503, detail={"code": exc.code}) from None
    except Exception:
        # No exception text, request headers, API keys or provider bodies in JSON.
        raise HTTPException(503, detail={"code": "CATALOG_UNAVAILABLE"}) from None
    finally:
        _slots.release()


@canonical_router.get("")
def canonical_catalog(request: Request):
    validate_request(request, set())
    return read_snapshot()


@router.get("")
def list_markets(
    request: Request,
    status: Literal["all", "open", "awaiting_resolution", "closed", "resolved", "cancelled"] = "all",
    category: str | None = Query(default=None, min_length=1, max_length=128),
    limit: int = Query(default=100, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    validate_request(request, {"status", "category", "limit", "offset"})
    data = read_snapshot()
    rows = [m for m in data["markets"]
            if (status == "all" or m["state"] == status)
            and (category is None or m["category"].casefold() == category.casefold())]
    # Keep the canonical snapshot envelope intact. The list view explicitly
    # identifies pagination; totals and digest describe the full snapshot.
    selected = rows[offset:offset + limit]
    return dict(data, markets=selected, total=len(rows), returned=len(selected),
                complete=len(selected) == data["market_count"],
                view={"status": status, "category": category, "offset": offset,
                      "limit": limit, "totals_scope": "full_snapshot",
                      "digest_scope": "full_snapshot"})


@router.get("/images/all")
def get_all_images(request: Request):
    validate_request(request, set())
    # Historical onchain_id alone does not identify a recovery market.
    # Do not associate legacy images with a different deployment.
    return {}


@router.get("/{market_id}")
@canonical_router.get("/{market_id}")
def get_market(market_id: str, request: Request):
    validate_request(request, set())
    if not re.fullmatch(r"(?:0|[1-9][0-9]?)", market_id):
        raise HTTPException(404, detail={"code": "MARKET_NOT_FOUND"})
    data = read_snapshot()
    row = next((m for m in data["markets"] if m["id"] == market_id), None)
    if row is None:
        raise HTTPException(404, detail={"code": "MARKET_NOT_FOUND"})
    result = {k: v for k, v in data.items() if k not in {"markets", "totals_by_currency"}}
    return dict(result, market=row)
