"""Resolution evidence generator for recovery.

This module NEVER signs or submits transactions. It only produces a deterministic,
auditable candidate result from the on-chain market configuration and a named
historical data source.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal

import httpx
from web3 import Web3

from app.core.config import settings

CHAIN_ID = 84532
PRICE_SCALE = Decimal("100000000")
MARKET_ABI = [{
    "inputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
    "name": "markets",
    "outputs": [
        {"internalType": "uint256", "name": "id", "type": "uint256"},
        {"internalType": "address", "name": "creator", "type": "address"},
        {"internalType": "string", "name": "question", "type": "string"},
        {"internalType": "string", "name": "category", "type": "string"},
        {"internalType": "string", "name": "assetSymbol", "type": "string"},
        {"internalType": "uint256", "name": "targetPrice", "type": "uint256"},
        {"internalType": "bool", "name": "targetAbove", "type": "bool"},
        {"internalType": "uint256", "name": "expiresAt", "type": "uint256"},
        {"internalType": "uint256", "name": "yesPool", "type": "uint256"},
        {"internalType": "uint256", "name": "noPool", "type": "uint256"},
        {"internalType": "uint256", "name": "yieldAccrued", "type": "uint256"},
        {"internalType": "uint8", "name": "status", "type": "uint8"},
        {"internalType": "uint8", "name": "outcome", "type": "uint8"},
        {"internalType": "address", "name": "resolver", "type": "address"},
        {"internalType": "uint8", "name": "currency", "type": "uint8"},
    ],
    "stateMutability": "view",
    "type": "function",
}]

SUPPORTED_BINANCE = {
    "BTC": "BTCUSDT",
    "ETH": "ETHUSDT",
    "SOL": "SOLUSDT",
    "BNB": "BNBUSDT",
    "XRP": "XRPUSDT",
    "ADA": "ADAUSDT",
    "DOGE": "DOGEUSDT",
    "LINK": "LINKUSDT",
    "LTC": "LTCUSDT",
}


def _market_tuple(raw):
    keys = [
        "id", "creator", "question", "category", "asset_symbol", "target_price_raw",
        "target_above", "expires_at", "yes_pool", "no_pool", "yield_accrued",
        "status", "outcome", "resolver", "currency",
    ]
    return dict(zip(keys, raw))


def _evidence_hash(payload: dict) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def get_market(market_id: int) -> dict:
    w3 = Web3(Web3.HTTPProvider(settings.BASE_SEPOLIA_RPC, request_kwargs={"timeout": 20}))
    if not w3.is_connected() or int(w3.eth.chain_id) != CHAIN_ID:
        raise RuntimeError("Base Sepolia RPC unavailable or wrong chain")
    contract = w3.eth.contract(
        address=Web3.to_checksum_address(settings.PREDICTION_MARKET_ADDRESS),
        abi=MARKET_ABI,
    )
    count_abi = [{
        "inputs": [], "name": "marketCount",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view", "type": "function",
    }]
    count_contract = w3.eth.contract(address=contract.address, abi=MARKET_ABI + count_abi)
    count = int(count_contract.functions.marketCount().call())
    if market_id < 0 or market_id >= count:
        raise ValueError("Market not found")
    return _market_tuple(count_contract.functions.markets(market_id).call())


async def binance_price_evidence(market: dict) -> dict:
    asset = (market["asset_symbol"] or "").strip().upper()
    pair = SUPPORTED_BINANCE.get(asset)
    if not pair:
        raise ValueError(f"No configured recovery price source for asset {asset or '(empty)'}")

    expires = int(market["expires_at"])
    minute_start_ms = (expires // 60) * 60 * 1000
    params = {
        "symbol": pair,
        "interval": "1m",
        "startTime": minute_start_ms,
        "endTime": minute_start_ms + 60_000,
        "limit": 1,
    }
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(settings.BINANCE_API_URL + "/klines", params=params)
        response.raise_for_status()
        rows = response.json()
    if not rows:
        raise RuntimeError("Historical price source returned no candle")

    row = rows[0]
    open_ms, close_price, close_ms = int(row[0]), Decimal(str(row[4])), int(row[6])
    if not (open_ms <= expires * 1000 <= close_ms):
        raise RuntimeError("Historical candle does not contain market expiry")

    target = Decimal(int(market["target_price_raw"])) / PRICE_SCALE
    if target <= 0:
        raise ValueError("Market has no on-chain targetPrice; automatic candidate is refused")

    yes_won = close_price > target if bool(market["target_above"]) else close_price < target
    evidence = {
        "schema": "cryptopredict-resolution-evidence-v1",
        "chain_id": CHAIN_ID,
        "contract": settings.PREDICTION_MARKET_ADDRESS.lower(),
        "market_id": int(market["id"]),
        "question": market["question"],
        "asset_symbol": asset,
        "rule": "strict_greater_than" if market["target_above"] else "strict_less_than",
        "target_price": format(target, "f"),
        "expires_at": datetime.fromtimestamp(expires, tz=timezone.utc).isoformat(),
        "source": {
            "provider": "Binance public market data",
            "endpoint": "/api/v3/klines",
            "symbol": pair,
            "interval": "1m",
            "policy": "close price of the 1-minute candle containing expires_at",
        },
        "observation": {
            "candle_open_at": datetime.fromtimestamp(open_ms / 1000, tz=timezone.utc).isoformat(),
            "candle_close_at": datetime.fromtimestamp(close_ms / 1000, tz=timezone.utc).isoformat(),
            "close_price": format(close_price, "f"),
        },
        "candidate": "YES" if yes_won else "NO",
        "yes_won": yes_won,
        "automatic_execution": False,
    }
    evidence["evidence_hash"] = _evidence_hash(evidence)
    return evidence


async def resolution_candidate(market_id: int) -> dict:
    market = get_market(market_id)
    now = int(datetime.now(tz=timezone.utc).timestamp())
    if int(market["status"]) != 0:
        raise ValueError("Market is not open")
    if now < int(market["expires_at"]):
        raise ValueError("Market has not expired")
    return await binance_price_evidence(market)
