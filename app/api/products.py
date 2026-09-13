from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas import ProductOut
from app.services import catalog_service

router = APIRouter(prefix="/api/products", tags=["products"])


@router.get("/by-game/{game_id}", response_model=list[ProductOut])
async def products_by_game(game_id: int, db: AsyncSession = Depends(get_db)):
    return await catalog_service.list_products_for_game(db, game_id)


@router.get("/{product_id}", response_model=ProductOut)
async def product_detail(product_id: int, db: AsyncSession = Depends(get_db)):
    product = await catalog_service.get_product(db, product_id)
    if not product or not product.is_active:
        raise HTTPException(404, "product_not_found")
    return product
