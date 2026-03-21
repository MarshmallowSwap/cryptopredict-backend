from fastapi import APIRouter
router = APIRouter()

@router.get("")
async def list_payouts():
    return {"message": "Payouts managed via market resolution"}
