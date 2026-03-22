from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional
import os, httpx

router = APIRouter(prefix="/api/v1/ai", tags=["ai"])

ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")

SYSTEM = """You are the CryptoPredict AI advisor. CryptoPredict is a 100% crypto-native prediction market on Base Sepolia. Key facts:
- Token: $CPRED (100M supply), presale Stage 1 at $0.050, listing target $0.150
- Markets: bet YES/NO on crypto/macro/sport events using ETH, USDC, USDT or CPRED
- Yield: 4.8% APY automatic on pool capital (simulated on testnet, real DeFi yield on mainnet via Aave)
- Staking: Flexible 12%, 30-day 20%, 90-day 28% APY in CPRED + ETH from protocol fees
- Fees: 2% on payout (1% creator + 1% stakers), 0% CPRED markets, 1% if you hold CPRED
- Create market: need 1,000 CPRED in wallet+staking
- Secondary market: sell open positions before expiry, 0.5% fee
- Trading: price chart from blockchain events + off-chain limit orderbook
- Governance: 1 CPRED = 1 vote, launches mainnet Q4 2025
- Currently on Base Sepolia testnet, mainnet after audit
Be concise (max 3 sentences). Answer in the same language the user writes in."""

class Message(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    messages: List[Message]

@router.post("/chat")
async def chat(req: ChatRequest):
    if not ANTHROPIC_KEY:
        raise HTTPException(503, "AI service not configured")
    
    # Limit history to last 10 messages to save tokens
    messages = [{"role": m.role, "content": m.content} for m in req.messages[-10:]]
    
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 300,
                "system": SYSTEM,
                "messages": messages,
            }
        )
    
    if resp.status_code != 200:
        raise HTTPException(502, "AI service error")
    
    data = resp.json()
    text = data["content"][0]["text"] if data.get("content") else "Sorry, no response."
    return {"reply": text}
