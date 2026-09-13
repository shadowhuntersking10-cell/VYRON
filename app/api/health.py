from fastapi import APIRouter

from app.config import settings
from app.database import check_connection
from app.payments.manager import get_payment_manager
from app.suppliers.manager import get_supplier_manager

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def health() -> dict:
    ok, detail = await check_connection()
    return {
        "status": "ok" if ok else "degraded",
        "db": "up" if ok else detail,
        "mysql": settings.using_mysql,
        "telegram": settings.telegram_configured,
        "payments": get_payment_manager().status_list(),
        "suppliers": get_supplier_manager().status_list(),
    }
