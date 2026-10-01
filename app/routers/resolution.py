from fastapi import APIRouter, HTTPException, Path
from app.services.resolution_evidence import resolution_candidate

router = APIRouter()


@router.get("/candidate/{market_id}")
async def get_resolution_candidate(market_id: int = Path(ge=0)):
    try:
        return await resolution_candidate(market_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Resolution evidence unavailable: {exc}") from exc
