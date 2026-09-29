from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List
import re


class Settings(BaseSettings):
    SUPABASE_URL: str
    SUPABASE_SERVICE_KEY: str = Field(repr=False)
    SECRET_KEY: str = Field(default="", repr=False)
    CORS_ORIGINS: List[str] = [
        "https://cryptopredict-chi.vercel.app", "https://cryptopredict.app",
        "http://localhost:3000", "http://localhost:5173",
    ]
    BINANCE_API_URL: str = "https://api.binance.com/api/v3"
    COINGECKO_API_URL: str = "https://api.coingecko.com/api/v3"
    # Legacy estimates only; these values cannot authorize or fund an accrual.
    YIELD_APY: float = 0.048
    YIELD_WINNER_SHARE: float = 0.50
    YIELD_STAKER_SHARE: float = 0.30
    YIELD_TREASURY_SHARE: float = 0.20
    PLATFORM_FEE: float = 0.02
    CREATOR_FEE: float = 0.01
    PROTOCOL_FEE: float = 0.01

    # Historical setting is retained for import compatibility, never for recovery auth.
    ADMIN_TOKEN: str = Field(default="", repr=False)
    RECOVERY_ADMIN_TOKEN: str = Field(default="", repr=False)
    WEBHOOK_SECRET: str = Field(default="", repr=False)

    @field_validator("RECOVERY_ADMIN_TOKEN")
    @classmethod
    def validate_recovery_token(cls, value: str) -> str:
        if value and (not re.fullmatch(r"[A-Za-z0-9_-]{48,256}", value)
                      or value.startswith("cp-admin-")):
            raise ValueError("Configure a fresh URL-safe recovery token of at least 48 characters")
        return value

    BASE_SEPOLIA_RPC: str = "https://gateway.tenderly.co/public/base-sepolia"
    PREDICTION_MARKET_ADDRESS: str = "0x775267160f3F7fb7908A7f2a4a2b0AFe22CD9e66"
    POSITION_MARKET_ADDRESS: str = "0xa241c72f7a7b120778e4fefab053c5f7e81c072a"
    AMM_POOL_ADDRESS: str = "0xaa645dca8a82764db9a725ab3ac9e2caab1440d0"
    CPRED_TOKEN_ADDRESS: str = "0xEc937bF3123874115EDcBBE1b3802C95f572e8E5"
    CPRED_PRESALE_ADDRESS: str = "0xC881FF7f99a666372DD0B9d50A9244E6564ea2B7"
    PRESALE_STAKING_ADDRESS: str = "0x6e9FE398C06E479Cd69663737415375e095c3454"
    MOCK_USDC_ADDRESS: str = "0x8A54f0e841CFCA5fA654912AF33cCD121D182311"
    MOCK_USDT_ADDRESS: str = "0xaBB48e1693Df04fb894843e52B239D5C5d0ab871"
    TEAM_WALLET_PRIVATE_KEY: str = Field(default="", repr=False)
    NOWPAYMENTS_API_KEY: str = Field(default="", repr=False)
    TELEGRAM_BOT_TOKEN: str = Field(default="", repr=False)
    model_config = SettingsConfigDict(env_file=".env", extra="allow", hide_input_in_errors=True)


settings = Settings()
