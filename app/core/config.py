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
    YIELD_APY: float = 0.048          # 4.8% annuo
    YIELD_WINNER_SHARE: float = 0.50  # 50% ai vincitori
    YIELD_STAKER_SHARE: float = 0.30  # 30% agli staker CPRED
    YIELD_TREASURY_SHARE: float = 0.20 # 20% treasury

    # Platform fees
    PLATFORM_FEE: float = 0.02        # 2% sulla vincita
    CREATOR_FEE: float = 0.01         # 1% al creatore
    PROTOCOL_FEE: float = 0.01        # 1% al protocollo

    # Admin
    ADMIN_TOKEN: str = "change-me-in-production"

    # NOWPayments (opzionale, fase 2)
    NOWPAYMENTS_API_KEY: str = ""

    # Telegram (opzionale, fase 2)
    TELEGRAM_BOT_TOKEN: str = ""

    class Config:
        env_file = ".env"
        extra = "allow"

settings = Settings()
