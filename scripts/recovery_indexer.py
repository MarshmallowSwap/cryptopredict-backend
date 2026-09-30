#!/usr/bin/env python3
"""Manual finalized-event indexer for the CryptoPredict recovery contract.

Properties:
- Base Sepolia only.
- No private key and no transaction signing.
- Writes only to recovery_chain_events and recovery_indexer_state.
- Idempotent on chain_id + contract_address + tx_hash + log_index.
- Indexes only blocks older than RECOVERY_INDEXER_CONFIRMATIONS.
- Safe to run repeatedly.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from eth_utils import event_signature_to_log_topic
from supabase import create_client
from web3 import Web3
from web3._utils.events import get_event_data

from app.core.config import settings

CHAIN_ID = 84532
EVENTS = [
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "internalType": "uint256", "name": "id", "type": "uint256"},
            {"indexed": False, "internalType": "address", "name": "creator", "type": "address"},
            {"indexed": False, "internalType": "string", "name": "question", "type": "string"},
            {"indexed": False, "internalType": "uint256", "name": "expiresAt", "type": "uint256"},
        ],
        "name": "MarketCreated", "type": "event",
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "internalType": "address", "name": "resolver", "type": "address"},
        ],
        "name": "ResolverAdded", "type": "event",
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "internalType": "address", "name": "resolver", "type": "address"},
        ],
        "name": "ResolverRemoved", "type": "event",
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": False, "internalType": "uint256", "name": "newMin", "type": "uint256"},
        ],
        "name": "MinCpredUpdated", "type": "event",
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "internalType": "uint256", "name": "marketId", "type": "uint256"},
            {"indexed": True, "internalType": "address", "name": "user", "type": "address"},
            {"indexed": False, "internalType": "bool", "name": "side", "type": "bool"},
            {"indexed": False, "internalType": "uint256", "name": "amount", "type": "uint256"},
        ],
        "name": "BetPlaced", "type": "event",
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "internalType": "uint256", "name": "id", "type": "uint256"},
            {"indexed": False, "internalType": "enum PredictionMarket.Outcome", "name": "outcome", "type": "uint8"},
            {"indexed": False, "internalType": "address", "name": "resolver", "type": "address"},
        ],
        "name": "MarketResolved", "type": "event",
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "internalType": "uint256", "name": "marketId", "type": "uint256"},
            {"indexed": True, "internalType": "address", "name": "user", "type": "address"},
            {"indexed": False, "internalType": "uint256", "name": "amount", "type": "uint256"},
        ],
        "name": "PayoutClaimed", "type": "event",
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "internalType": "uint256", "name": "id", "type": "uint256"},
        ],
        "name": "MarketCancelled", "type": "event",
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "internalType": "uint256", "name": "marketId", "type": "uint256"},
            {"indexed": True, "internalType": "address", "name": "user", "type": "address"},
            {"indexed": False, "internalType": "uint256", "name": "amount", "type": "uint256"},
        ],
        "name": "RefundClaimed", "type": "event",
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "internalType": "uint256", "name": "marketId", "type": "uint256"},
            {"indexed": True, "internalType": "address", "name": "from", "type": "address"},
            {"indexed": True, "internalType": "address", "name": "to", "type": "address"},
            {"indexed": False, "internalType": "uint256", "name": "amount", "type": "uint256"},
        ],
        "name": "PositionTransferred", "type": "event",
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "internalType": "uint256", "name": "marketId", "type": "uint256"},
            {"indexed": False, "internalType": "enum PredictionMarket.Currency", "name": "currency", "type": "uint8"},
            {"indexed": False, "internalType": "uint256", "name": "creatorFee", "type": "uint256"},
            {"indexed": False, "internalType": "uint256", "name": "protocolFee", "type": "uint256"},
        ],
        "name": "FeesAccrued", "type": "event",
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "internalType": "address", "name": "creator", "type": "address"},
            {"indexed": False, "internalType": "enum PredictionMarket.Currency", "name": "currency", "type": "uint8"},
            {"indexed": False, "internalType": "address", "name": "recipient", "type": "address"},
            {"indexed": False, "internalType": "uint256", "name": "amount", "type": "uint256"},
        ],
        "name": "CreatorFeesClaimed", "type": "event",
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": False, "internalType": "enum PredictionMarket.Currency", "name": "currency", "type": "uint8"},
            {"indexed": False, "internalType": "address", "name": "recipient", "type": "address"},
            {"indexed": False, "internalType": "uint256", "name": "amount", "type": "uint256"},
        ],
        "name": "ProtocolFeesWithdrawn", "type": "event",
    },
]


def signature(abi: dict[str, Any]) -> str:
    return f"{abi['name']}({','.join(i['type'] for i in abi['inputs'])})"


def json_value(value: Any) -> Any:
    if isinstance(value, (bytes, bytearray)):
        return "0x" + bytes(value).hex()
    if hasattr(value, "hex") and not isinstance(value, str):
        try:
            return value.hex()
        except Exception:
            pass
    if isinstance(value, int):
        return str(value)
    if isinstance(value, dict):
        return {k: json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(v) for v in value]
    return value


def event_row(decoded: dict[str, Any], log: Any, timestamp: datetime, contract: str) -> dict[str, Any]:
    args = dict(decoded["args"])
    name = decoded["event"]
    market_id = args.get("marketId", args.get("id"))
    actor = (
        args.get("user")
        or args.get("creator")
        or args.get("from")
        or args.get("resolver")
        or args.get("recipient")
    )
    amount = args.get("amount")
    if name == "FeesAccrued":
        amount = int(args["creatorFee"]) + int(args["protocolFee"])

    row = {
        "chain_id": CHAIN_ID,
        "contract_address": contract.lower(),
        "block_number": int(log["blockNumber"]),
        "block_hash": log["blockHash"].hex(),
        "tx_hash": log["transactionHash"].hex(),
        "tx_index": int(log["transactionIndex"]),
        "log_index": int(log["logIndex"]),
        "event_name": name,
        "market_id": str(market_id) if market_id is not None else None,
        "actor": str(actor).lower() if actor else None,
        "side": args.get("side"),
        "amount_raw": str(amount) if amount is not None else None,
        "currency": int(args["currency"]) if "currency" in args else None,
        "outcome": int(args["outcome"]) if "outcome" in args else None,
        "payload": json_value(args),
        "block_timestamp": timestamp.isoformat(),
        "canonical": True,
    }
    return row


def main() -> None:
    w3 = Web3(Web3.HTTPProvider(settings.BASE_SEPOLIA_RPC, request_kwargs={"timeout": 20}))
    if not w3.is_connected():
        raise RuntimeError("Base Sepolia RPC unavailable")
    if int(w3.eth.chain_id) != CHAIN_ID:
        raise RuntimeError(f"Wrong chain: {w3.eth.chain_id}")

    contract = Web3.to_checksum_address(settings.PREDICTION_MARKET_ADDRESS)
    if w3.eth.get_code(contract) in (b"", b"\x00"):
        raise RuntimeError("PredictionMarket bytecode missing")

    deploy_receipt = w3.eth.get_transaction_receipt(settings.RECOVERY_DEPLOYMENT_TX_HASH)
    if not deploy_receipt or not deploy_receipt.get("blockNumber"):
        raise RuntimeError("Recovery deployment receipt not found")
    deployment_block = int(deploy_receipt["blockNumber"])

    confirmations = max(1, int(settings.RECOVERY_INDEXER_CONFIRMATIONS))
    span = max(1, min(5000, int(settings.RECOVERY_INDEXER_BLOCK_SPAN)))
    latest = int(w3.eth.block_number)
    finalized = latest - confirmations
    if finalized < deployment_block:
        print("No finalized recovery blocks yet.")
        return

    sb = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY)
    state_res = (
        sb.table("recovery_indexer_state")
        .select("*")
        .eq("chain_id", CHAIN_ID)
        .eq("contract_address", contract.lower())
        .limit(1)
        .execute()
    )
    state = (state_res.data or [None])[0]
    start = deployment_block if not state else max(deployment_block, int(state["last_finalized_block"]) + 1)

    topic_map = {
        event_signature_to_log_topic(signature(abi)).hex(): abi
        for abi in EVENTS
    }
    timestamps: dict[int, datetime] = {}
    total = 0

    if start <= finalized:
        for first in range(start, finalized + 1, span):
            last = min(finalized, first + span - 1)
            logs = w3.eth.get_logs({"address": contract, "fromBlock": first, "toBlock": last})
            rows = []
            for log in logs:
                topic0 = log["topics"][0].hex()
                abi = topic_map.get(topic0)
                if not abi:
                    continue
                decoded = get_event_data(w3.codec, abi, log)
                block_no = int(log["blockNumber"])
                if block_no not in timestamps:
                    block = w3.eth.get_block(block_no)
                    timestamps[block_no] = datetime.fromtimestamp(int(block["timestamp"]), tz=timezone.utc)
                rows.append(event_row(decoded, log, timestamps[block_no], contract))

            if rows:
                (
                    sb.table("recovery_chain_events")
                    .upsert(rows, on_conflict="chain_id,contract_address,tx_hash,log_index")
                    .execute()
                )
                total += len(rows)
            print(f"indexed blocks {first}-{last}: {len(rows)} events")

    final_block = w3.eth.get_block(finalized)
    state_row = {
        "chain_id": CHAIN_ID,
        "contract_address": contract.lower(),
        "deployment_tx_hash": settings.RECOVERY_DEPLOYMENT_TX_HASH.lower(),
        "start_block": deployment_block,
        "last_finalized_block": finalized,
        "last_finalized_hash": final_block["hash"].hex(),
        "confirmations": confirmations,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    (
        sb.table("recovery_indexer_state")
        .upsert(state_row, on_conflict="chain_id,contract_address")
        .execute()
    )

    print(
        f"OK chain={CHAIN_ID} contract={contract} deployment_block={deployment_block} "
        f"finalized={finalized} events_written={total}"
    )


if __name__ == "__main__":
    main()
