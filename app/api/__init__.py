from fastapi import APIRouter

from app.api import (
    admin, auth, donations, favorites, games, marketplace, notifications,
    orders, payments, products, reviews, support, users, wallet,
)

api_router = APIRouter()
for router in (auth.router, users.router, games.router, products.router, orders.router,
               payments.router, marketplace.router, donations.router, wallet.router,
               reviews.router, favorites.router, support.router, notifications.router,
               admin.router):
    api_router.include_router(router)
