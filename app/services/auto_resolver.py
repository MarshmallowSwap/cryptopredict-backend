"""
Auto-Resolver Cron — CryptoPredict
Gira ogni 5 minuti, controlla mercati scaduti e li risolve automaticamente.

Categorie con risoluzione automatica:
  - crypto / macro / defi → prezzo da Binance/CoinGecko
  - altre categorie → log "richiede risoluzione manuale" (team usa admin panel)

Il cron firma le transazioni con il TEAM_WALLET_PRIVATE_KEY dal .env
"""

import os, asyncio, logging
from datetime import datetime, timezone
from web3 import Web3
from app.core.supabase import get_supabase
from app.services.price_feed import get_asset_price

log = logging.getLogger("auto_resolver")

# ABI minima per resolveMarket e cancelMarket
MARKET_ABI = [
    {"name": "marketCount",    "type": "function", "stateMutability": "view",
     "inputs": [], "outputs": [{"type": "uint256"}]},
    {"name": "getMarket",      "type": "function", "stateMutability": "view",
     "inputs": [{"name": "id", "type": "uint256"}],
     "outputs": [{"components": [
         {"name": "id",          "type": "uint256"},
         {"name": "creator",     "type": "address"},
         {"name": "question",    "type": "string"},
         {"name": "category",    "type": "string"},
         {"name": "assetSymbol", "type": "string"},
         {"name": "targetPrice", "type": "uint256"},
         {"name": "targetAbove", "type": "bool"},
         {"name": "expiresAt",   "type": "uint256"},
         {"name": "yesPool",     "type": "uint256"},
         {"name": "noPool",      "type": "uint256"},
         {"name": "yieldAccrued","type": "uint256"},
         {"name": "status",      "type": "uint8"},
         {"name": "outcome",     "type": "uint8"},
         {"name": "resolver",    "type": "address"},
     ], "type": "tuple"}]},
    {"name": "resolveMarket",  "type": "function", "stateMutability": "nonpayable",
     "inputs": [{"name": "marketId", "type": "uint256"}, {"name": "yesWon", "type": "bool"}],
     "outputs": []},
    {"name": "cancelMarket",   "type": "function", "stateMutability": "nonpayable",
     "inputs": [{"name": "marketId", "type": "uint256"}], "outputs": []},
]

# Categorie con auto-resolve via price feed
AUTO_RESOLVE_CATEGORIES = {"crypto", "macro", "defi"}

def get_w3():
    rpc = os.getenv("BASE_SEPOLIA_RPC", "https://sepolia.base.org")
    return Web3(Web3.HTTPProvider(rpc))

def get_contract(w3):
    addr = os.getenv("PREDICTION_MARKET_ADDRESS", "0x5264C5212b57ca1bf412b104165Cbd8173aD6F11")
    return w3.eth.contract(address=Web3.to_checksum_address(addr), abi=MARKET_ABI)

def get_team_account(w3):
    pk = os.getenv("TEAM_WALLET_PRIVATE_KEY", "")
    if not pk:
        raise ValueError("TEAM_WALLET_PRIVATE_KEY non impostata nel .env")
    return w3.eth.account.from_key(pk)

async def resolve_tx(w3, contract, account, market_id: int, yes_won: bool) -> str:
    """Firma e invia resolveMarket on-chain. Ritorna il tx hash."""
    nonce   = w3.eth.get_transaction_count(account.address)
    gas_price = w3.eth.gas_price
    tx = contract.functions.resolveMarket(market_id, yes_won).build_transaction({
        "from":     account.address,
        "nonce":    nonce,
        "gas":      200_000,
        "gasPrice": int(gas_price * 1.2),
    })
    signed  = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    if receipt.status != 1:
        raise Exception(f"TX revertita: {tx_hash.hex()}")
    return tx_hash.hex()

async def auto_resolve_price_market(w3, contract, account, market) -> dict:
    """Risolve un mercato crypto/macro controllando il prezzo attuale."""
    asset        = market["assetSymbol"]
    target_price = market["targetPrice"] / 1e8  # contratto usa 8 decimali
    target_above = market["targetAbove"]

    if not asset or asset == "OTHER" or target_price == 0:
        return {"action": "skip", "reason": "no price target"}

    try:
        current_price = await get_asset_price(asset)
        yes_won = (current_price >= target_price) if target_above else (current_price < target_price)

        log.info(f"  Market #{market['id']}: {asset} = ${current_price:.2f} "
                 f"{'≥' if target_above else '<'} ${target_price:.2f} → {'YES' if yes_won else 'NO'}")

        tx = await resolve_tx(w3, contract, account, market["id"], yes_won)
        return {"action": "resolved", "yes_won": yes_won, "tx": tx,
                "price": current_price, "target": target_price}
    except Exception as e:
        log.error(f"  Errore auto-resolve #{market['id']}: {e}")
        return {"action": "error", "reason": str(e)}

async def run_auto_resolver():
    """
    Entry point del cron — chiamato ogni 5 minuti da start.py
    """
    log.info(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] Auto-resolver avviato")

    try:
        w3       = get_w3()
        contract = get_contract(w3)
        account  = get_team_account(w3)
    except Exception as e:
        log.error(f"Setup fallito: {e}")
        return

    now   = int(datetime.now(timezone.utc).timestamp())
    count = contract.functions.marketCount().call()
    log.info(f"  Mercati totali: {count}")

    resolved_count = 0
    manual_needed  = []

    for market_id in range(count):
        try:
            raw = contract.functions.getMarket(market_id).call()
            market = {
                "id":          raw[0],
                "question":    raw[2],
                "category":    raw[3].lower(),
                "assetSymbol": raw[4],
                "targetPrice": raw[5],
                "targetAbove": raw[6],
                "expiresAt":   raw[7],
                "yesPool":     raw[8],
                "noPool":      raw[9],
                "status":      raw[11],  # 0=Open 1=Closed 2=Resolved 3=Cancelled
            }

            # Salta se non è Open o non è scaduto
            if market["status"] != 0:
                continue
            if market["expiresAt"] > now:
                continue

            log.info(f"  Mercato #{market_id} scaduto: '{market['question'][:60]}'")

            cat = market["category"]

            if cat in AUTO_RESOLVE_CATEGORIES:
                # Auto-resolve via price feed
                result = await auto_resolve_price_market(w3, contract, account, market)
                if result["action"] == "resolved":
                    resolved_count += 1
                    log.info(f"  OK #{market_id} risolto automaticamente ({result['tx'][:10]}...)")
                    # Aggiorna anche Supabase
                    try:
                        sb = get_supabase()
                        sb.table("markets").update({
                            "status":  "resolved",
                            "outcome": "YES" if result["yes_won"] else "NO",
                            "resolved_at": datetime.now(timezone.utc).isoformat()
                        }).eq("onchain_id", market_id).execute()
                    except: pass
                elif result["action"] == "skip":
                    # Nessun target price — aggiungi alla lista manuale
                    manual_needed.append(market)
                    log.warning(f"  #{market_id} ({cat}) senza target price - richiede risoluzione manuale")
            else:
                # Sport, politica, entertainment, scienza, geopolitica → manuale
                manual_needed.append(market)
                log.info(f"  #{market_id} ({cat}) - richiede risoluzione manuale dal team")

        except Exception as e:
            log.error(f"  Errore mercato #{market_id}: {e}")
            continue

    # Summary
    log.info(f"  ─────────────────────────────────────")
    log.info(f"  Risolti automaticamente: {resolved_count}")
    log.info(f"  Da risolvere manualmente: {len(manual_needed)}")
    if manual_needed:
        log.info(f"  → Usa admin panel: https://cryptopredict-chi.vercel.app/admin.html")
        for m in manual_needed:
            log.info("    #" + str(m['id']) + " [" + m['category'] + "] " + m['question'][:50])

    return {"resolved": resolved_count, "manual": len(manual_needed)}
