"""
Price feed service — chiama Binance/CoinGecko per prezzi live.
Usato per auto-resolution dei mercati price_target.
"""
import httpx
from app.core.config import settings

SYMBOL_MAP = {
    "BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana",
    "BNB": "binancecoin", "XRP": "ripple", "ADA": "cardano",
    "AVAX": "avalanche-2", "MATIC": "matic-network", "DOT": "polkadot",
    "UNI": "uniswap", "LINK": "chainlink", "AAVE": "aave",
}

async def get_asset_price(symbol: str) -> float:
    """Ritorna il prezzo USDT di un asset da Binance."""
    symbol = symbol.upper()
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(
                f"{settings.BINANCE_API_URL}/ticker/price",
                params={"symbol": f"{symbol}USDT"}
            )
            data = r.json()
            if "price" in data:
                return float(data["price"])
    except Exception:
        pass

    # Fallback: CoinGecko
    cg_id = SYMBOL_MAP.get(symbol)
    if cg_id:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(
                    f"{settings.COINGECKO_API_URL}/simple/price",
                    params={"ids": cg_id, "vs_currencies": "usd"}
                )
                data = r.json()
                return float(data[cg_id]["usd"])
        except Exception:
            pass

    raise ValueError(f"Cannot fetch price for {symbol}")


async def check_price_target(
    asset_symbol: str,
    target_price: float,
    direction: str  # 'above' | 'below'
) -> bool | None:
    """Controlla se un target price è stato raggiunto. Ritorna None se errore."""
    try:
        current = await get_asset_price(asset_symbol)
        if direction == "above":
            return current >= target_price
        elif direction == "below":
            return current <= target_price
        return None
    except Exception:
        return None


async def get_multiple_prices(symbols: list[str]) -> dict[str, float]:
    """Prezzi multipli in una sola chiamata CoinGecko."""
    cg_ids = [SYMBOL_MAP.get(s.upper()) for s in symbols if SYMBOL_MAP.get(s.upper())]
    if not cg_ids:
        return {}
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(
                f"{settings.COINGECKO_API_URL}/simple/price",
                params={"ids": ",".join(cg_ids), "vs_currencies": "usd"}
            )
            data = r.json()
            result = {}
            for sym in symbols:
                cg_id = SYMBOL_MAP.get(sym.upper())
                if cg_id and cg_id in data:
                    result[sym.upper()] = float(data[cg_id]["usd"])
            return result
    except Exception:
        return {}
