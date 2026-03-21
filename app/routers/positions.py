from fastapi import APIRouter
router = APIRouter()

@router.get("")
async def list_positions():
    return {"message": "Use /users/{user_id}/positions"}
