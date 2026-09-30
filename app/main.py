from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import markets, positions, users, payouts, admin, chain, resolution
from app.services.yield_engine import router as yield_router
from app.core.config import settings
from app.core.recovery import MODE, RecoveryGuard

app = FastAPI(title="CryptoPredict API", version="1.1.0-recovery",
              description="Read-only recovery API. Legacy balances are unverified; monetary writes are disabled.")
app.state.recovery_admin_token = settings.RECOVERY_ADMIN_TOKEN
app.add_middleware(RecoveryGuard, admin_token=settings.RECOVERY_ADMIN_TOKEN)
# Last added middleware is outermost; valid CORS preflights stop here.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_origin_regex=r"https://cryptopredict(?:-[a-zA-Z0-9-]+)?-vaultworlds-projects\.vercel\.app",
    allow_credentials=False,
    allow_methods=["GET", "HEAD", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(markets.router, prefix="/api/v1/markets", tags=["Markets"])
app.include_router(positions.router, prefix="/api/v1/positions", tags=["Positions"])
app.include_router(users.router, prefix="/api/v1/users", tags=["Users"])
app.include_router(payouts.router, prefix="/api/v1/payouts", tags=["Payouts"])
app.include_router(yield_router, prefix="/api/v1/yield", tags=["Yield"])
app.include_router(admin.router, prefix="/api/v1/admin", tags=["Admin"])
app.include_router(chain.router, prefix="/api/v1/chain", tags=["Recovery Chain Index"])
app.include_router(resolution.router, prefix="/api/v1/resolution", tags=["Recovery Resolution"])


@app.get("/")
async def root():
    return {"status": "ok", "service": "CryptoPredict API", "mode": MODE}


@app.get("/health")
async def health():
    # Liveness only: do not claim database or blockchain readiness.
    return {"status": "alive", "mode": MODE, "readiness_verified": False}


@app.get("/api/v1/system/status")
async def system_status():
    return {
        "mode": MODE,
        "api_writes_enabled": False,
        "auto_resolver_enabled": False,
        "yield_accrual_enabled": False,
        "legacy_balances_verified": False,
        "chain_state_verified": False,
        "chain": {
            "name": "Base Sepolia",
            "chain_id": 84532,
            "prediction_market": settings.PREDICTION_MARKET_ADDRESS,
            "cpred": settings.CPRED_TOKEN_ADDRESS,
            "mock_usdc": settings.MOCK_USDC_ADDRESS,
            "mock_usdt": settings.MOCK_USDT_ADDRESS,
            "position_market_enabled": settings.POSITION_MARKET_ADDRESS
                != "0x0000000000000000000000000000000000000000",
            "amm_enabled": settings.AMM_POOL_ADDRESS
                != "0x0000000000000000000000000000000000000000",
            "presale_staking_enabled": settings.PRESALE_STAKING_ADDRESS
                != "0x0000000000000000000000000000000000000000",
        },
        "transport": {
            "expected_public_scheme": "https",
            "direct_uvicorn_public_exposure": False,
        },
    }
