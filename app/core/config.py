from pydantic_settings import BaseSettings
from typing import List

class Settings(BaseSettings):
    # Supabase
    SUPABASE_URL: str
    SUPABASE_SERVICE_KEY: str

    # App
    SECRET_KEY: str = "change-me-in-production"
    CORS_ORIGINS: List[str] = [
        "https://cryptopredict-chi.vercel.app",
        "https://cryptopredict.app",
        "http://localhost:3000",
        "http://localhost:5173",
    ]

    # Price feeds
    BINANCE_API_URL: str = "https://api.binance.com/api/v3"
    COINGECKO_API_URL: str = "https://api.coingecko.com/api/v3"

    # Yield
    YIELD_APY: float = 0.048           # 4.8% annuo
    YIELD_WINNER_SHARE: float = 0.50   # 50% vincitori
    YIELD_STAKER_SHARE: float = 0.30   # 30% staker CPRED
    YIELD_TREASURY_SHARE: float = 0.20 # 20% treasury

    # Platform fees
    PLATFORM_FEE: float = 0.02   # 2% sulla vincita
    CREATOR_FEE: float = 0.01    # 1% al creatore
    PROTOCOL_FEE: float = 0.01   # 1% al protocollo

    # Admin
    ADMIN_TOKEN: str = "cp-admin-f959e84282b17f83cb5626ae609991ff"

    # ── Smart Contracts — Base Sepolia v2 ────────────────────────────
    BASE_SEPOLIA_RPC: str = "https://gateway.tenderly.co/public/base-sepolia"
    PREDICTION_MARKET_ADDRESS: str = "0x775267160f3F7fb7908A7f2a4a2b0AFe22CD9e66"
    POSITION_MARKET_ADDRESS: str = "0xa241c72f7a7b120778e4fefab053c5f7e81c072a"
    AMM_POOL_ADDRESS: str = "0xaa645dca8a82764db9a725ab3ac9e2caab1440d0"
    CPRED_TOKEN_ADDRESS: str = "0xEc937bF3123874115EDcBBE1b3802C95f572e8E5"
    CPRED_PRESALE_ADDRESS: str = "0xC881FF7f99a666372DD0B9d50A9244E6564ea2B7"
    PRESALE_STAKING_ADDRESS: str = "0x6e9FE398C06E479Cd69663737415375e095c3454"
    MOCK_USDC_ADDRESS: str = "0x8A54f0e841CFCA5fA654912AF33cCD121D182311"
    MOCK_USDT_ADDRESS: str = "0xaBB48e1693Df04fb894843e52B239D5C5d0ab871"
    TEAM_WALLET_PRIVATE_KEY: str = ""

    # NOWPayments (optional)
    NOWPAYMENTS_API_KEY: str = ""

    # Telegram (optional)
    TELEGRAM_BOT_TOKEN: str = ""

    class Config:
        env_file = ".env"
        extra = "allow"

settings = Settings()
