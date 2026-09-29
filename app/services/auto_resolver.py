"""Legacy resolver quarantined during recovery.

The previous implementation resolved expired markets using the current price
and a team signing key. Do not restore it before historical-price semantics,
ABI/bytecode alignment and operator permissions have been verified.
The implementation remains available in git history; no signing key is loaded here.
"""
from app.core.recovery import block_legacy_write


async def run_auto_resolver():
    return {"status": "disabled", "reason": "recovery-read-only", "resolved": 0, "manual": 0}


async def resolve_tx(w3, contract, account, market_id: int, yes_won: bool) -> str:
    block_legacy_write("on-chain resolution")


async def auto_resolve_price_market(w3, contract, account, market) -> dict:
    block_legacy_write("current-price legacy resolution")
