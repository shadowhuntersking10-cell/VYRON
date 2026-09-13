from fastapi import APIRouter

from app.payments.manager import get_payment_manager

router = APIRouter(prefix="/api/payments", tags=["payments"])


@router.get("/providers")
async def providers() -> dict:
    return {"providers": get_payment_manager().status_list()}
