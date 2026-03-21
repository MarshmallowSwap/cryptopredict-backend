from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import markets, positions, users, payouts, admin
from app.services.yield_engine import router as yield_router
from app.core.config import settings

app = FastAPI(
    title="CryptoPredict API",
    version="1.0.0",
    description="Prediction market backend — markets, pools, positions, yield, payouts"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(markets.router,   prefix="/api/v1/markets",   tags=["Markets"])
app.include_router(positions.router, prefix="/api/v1/positions", tags=["Positions"])
app.include_router(users.router,     prefix="/api/v1/users",     tags=["Users"])
app.include_router(payouts.router,   prefix="/api/v1/payouts",   tags=["Payouts"])
app.include_router(yield_router,     prefix="/api/v1/yield",     tags=["Yield"])
app.include_router(admin.router,     prefix="/api/v1/admin",     tags=["Admin"])

@app.get("/")
async def root():
    return {"status": "ok", "service": "CryptoPredict API v1.0"}

@app.get("/health")
async def health():
    return {"status": "healthy"}
