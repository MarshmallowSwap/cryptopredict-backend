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
    RECOVERY_DEPLOYMENT_TX_HASH: str = "0xd5a65564232a9f3681c45c27e7829c34e8955ed7c9f67d46a7428e75dc351f74"
    RECOVERY_INDEXER_CONFIRMATIONS: int = 12
    RECOVERY_INDEXER_BLOCK_SPAN: int = 1000
    # Recovery deployment verified on Base Sepolia, 2026-09-30.
    PREDICTION_MARKET_ADDRESS: str = "0x76f9660a8801f97a8F5D1AC2036b9a9C22495436"
    # Legacy extensions stay disconnected during recovery.
    POSITION_MARKET_ADDRESS: str = "0x0000000000000000000000000000000000000000"
    AMM_POOL_ADDRESS: str = "0x0000000000000000000000000000000000000000"
    CPRED_TOKEN_ADDRESS: str = "0xEc937bF3123874115EDcBBE1b3802C95f572e8E5"
    CPRED_PRESALE_ADDRESS: str = "0xC881FF7f99a666372DD0B9d50A9244E6564ea2B7"
    PRESALE_STAKING_ADDRESS: str = "0x0000000000000000000000000000000000000000"
    MOCK_USDC_ADDRESS: str = "0x8A54f0e841CFCA5fA654912AF33cCD121D182311"
    MOCK_USDT_ADDRESS: str = "0xaBB48e1693Df04fb894843e52B239D5C5d0ab871"
    NOWPAYMENTS_API_KEY: str = Field(default="", repr=False)
    TELEGRAM_BOT_TOKEN: str = Field(default="", repr=False)
    model_config = SettingsConfigDict(env_file=".env", extra="allow", hide_input_in_errors=True)


settings = Settings()
