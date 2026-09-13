#!/usr/bin/env python3
"""
VYRON - Gaming Commerce Platform
Single command startup: python main.py

Orchestrates:
1. FastAPI backend
2. Public website
3. Telegram Bot
4. Telegram Mini App backend
5. Background workers/tasks
6. Scheduled jobs
"""
from __future__ import annotations
import asyncio
import logging
import signal
import sys
import os
from pathlib import Path

# Ensure app is in path
sys.path.insert(0, str(Path(__file__).parent))

from app.config import settings

# Logging setup
logging.basicConfig(
    level=logging.INFO if settings.is_development else logging.WARNING,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("vyron.log") if not settings.is_development else logging.NullHandler()
    ]
)
logger = logging.getLogger("vyron.main")
# Reduce noisy loggers
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

# Global flag for shutdown
shutdown_event = asyncio.Event()

async def run_background_workers():
    """Background workers for order processing, cleanup, etc"""
    logger.info("Starting background workers...")
    
    while not shutdown_event.is_set():
        try:
            # Order processing worker
            await process_pending_orders()
            
            # Cleanup expired sessions
            await cleanup_expired_sessions()
            
            # Check supplier orders
            await check_supplier_orders()
            
            # Wait 30 seconds
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            logger.info("Background workers cancelled")
            break
        except Exception as e:
            logger.error(f"Background worker error: {e}")
            await asyncio.sleep(10)

async def process_pending_orders():
    """Process orders that are PAID and need supplier fulfillment"""
    if not settings.SUPPLIER_ORDERS_ENABLED:
        return
    
    try:
        from app.database import AsyncSessionLocal
        from sqlalchemy import select
        from app.models.models import Order, SupplierOrder
        from app.suppliers.providers import get_supplier
        from app.utils.security import generate_idempotency_key
        from datetime import datetime

        async with AsyncSessionLocal() as db:
            # Find PAID orders without supplier order
            result = await db.execute(
                select(Order).where(Order.status == "PAID").limit(10)
            )
            orders = result.scalars().all()
            
            for order in orders:
                # Check if supplier order exists
                result = await db.execute(
                    select(SupplierOrder).where(SupplierOrder.order_id == order.id)
                )
                if result.scalar_one_or_none():
                    continue
                
                # Create supplier order
                supplier = get_supplier()
                # Get first product's supplier info
                from app.models.models import OrderItem, Product
                result = await db.execute(
                    select(OrderItem).where(OrderItem.order_id == order.id).limit(1)
                )
                item = result.scalar_one_or_none()
                if not item:
                    continue
                
                result = await db.execute(
                    select(Product).where(Product.id == item.product_id)
                )
                product = result.scalar_one_or_none()
                if not product:
                    continue

                idempotency_key = generate_idempotency_key()
                supplier_result = await supplier.create_order(
                    product_id=product.supplier_product_id or str(product.id),
                    quantity=item.quantity,
                    game_data=order.game_data or {},
                    idempotency_key=idempotency_key
                )

                # Create supplier order record
                s_order = SupplierOrder(
                    order_id=order.id,
                    supplier_id=None,  # Could map supplier id
                    supplier_order_id=supplier_result.get("supplier_order_id"),
                    supplier_product_id=product.supplier_product_id,
                    cost_price=product.supplier_cost,
                    status=supplier_result.get("status", "MANUAL_REVIEW"),
                    request_payload={"product_id": product.id, "game_data": order.game_data},
                    response_payload=supplier_result,
                    idempotency_key=idempotency_key
                )
                db.add(s_order)
                
                # Update order status
                if supplier_result.get("status") == "MANUAL_REVIEW":
                    order.status = "MANUAL_REVIEW"
                elif supplier_result.get("success"):
                    order.status = "SUPPLIER_PROCESSING"
                else:
                    order.status = "MANUAL_REVIEW"
                
                await db.commit()
                logger.info(f"Created supplier order for {order.order_number}: {supplier_result.get('status')}")

    except Exception as e:
        logger.error(f"process_pending_orders error: {e}")

async def cleanup_expired_sessions():
    """Cleanup expired user sessions"""
    try:
        from app.database import AsyncSessionLocal
        from sqlalchemy import delete
        from app.models.models import UserSession
        from datetime import datetime
        
        async with AsyncSessionLocal() as db:
            await db.execute(
                delete(UserSession).where(UserSession.expires_at < datetime.utcnow())
            )
            await db.commit()
    except Exception as e:
        logger.debug(f"cleanup sessions error: {e}")

async def check_supplier_orders():
    """Check status of supplier orders in PROCESSING"""
    try:
        from app.database import AsyncSessionLocal
        from sqlalchemy import select
        from app.models.models import SupplierOrder, Order
        from app.suppliers.providers import get_supplier
        from datetime import datetime, timedelta

        async with AsyncSessionLocal() as db:
            # Find supplier orders that are PROCESSING and not checked recently
            cutoff = datetime.utcnow() - timedelta(minutes=5)
            result = await db.execute(
                select(SupplierOrder).where(
                    SupplierOrder.status == "PROCESSING",
                    (SupplierOrder.last_checked_at == None) | (SupplierOrder.last_checked_at < cutoff)
                ).limit(5)
            )
            s_orders = result.scalars().all()
            
            supplier = get_supplier()
            for s_order in s_orders:
                if not s_order.supplier_order_id:
                    continue
                
                status_result = await supplier.get_order_status(s_order.supplier_order_id)
                s_order.last_checked_at = datetime.utcnow()
                
                if status_result.get("success"):
                    data = status_result.get("data", {})
                    new_status = data.get("status", "PROCESSING")
                    
                    if new_status in ("COMPLETED", "SUCCESS"):
                        s_order.status = "COMPLETED"
                        # Update main order
                        result = await db.execute(select(Order).where(Order.id == s_order.order_id))
                        order = result.scalar_one_or_none()
                        if order:
                            order.status = "COMPLETED"
                            order.completed_at = datetime.utcnow()
                            logger.info(f"Order {order.order_number} completed via supplier")
                    elif new_status in ("FAILED", "CANCELLED"):
                        s_order.status = new_status
                        result = await db.execute(select(Order).where(Order.id == s_order.order_id))
                        order = result.scalar_one_or_none()
                        if order:
                            order.status = "FAILED"
                
                await db.commit()

    except Exception as e:
        logger.error(f"check_supplier_orders error: {e}")

async def run_scheduler():
    """Scheduled jobs"""
    logger.info("Starting scheduler...")
    while not shutdown_event.is_set():
        try:
            # Daily revenue aggregation, etc
            await asyncio.sleep(3600)  # hourly
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Scheduler error: {e}")
            await asyncio.sleep(60)

async def start_telegram_bot_task():
    """Start Telegram bot polling as background task"""
    if not settings.TELEGRAM_BOT_TOKEN:
        logger.info("Telegram bot token not configured, skipping bot")
        return

    try:
        from app.telegram.bot import start_telegram_bot
        logger.info("Starting Telegram bot...")
        await start_telegram_bot()
    except asyncio.CancelledError:
        logger.info("Telegram bot task cancelled")
    except Exception as e:
        logger.error(f"Telegram bot error: {e}")

async def main_async():
    """Main async orchestrator"""
    logger.info("="*60)
    logger.info(f"VYRON Starting - Environment: {settings.APP_ENV}")
    logger.info(f"App URL: {settings.APP_URL}")
    logger.info(f"Database: {settings.effective_database_url.split('@')[-1] if '@' in settings.effective_database_url else settings.effective_database_url}")
    logger.info("="*60)

    # Check database
    from app.database import check_db_connection, init_db
    db_ok = await check_db_connection()
    if not db_ok:
        logger.warning("⚠️  Database connection failed!")
        logger.warning("   If using MySQL, check MYSQL_* env vars or DATABASE_URL")
        logger.warning("   For development, set DATABASE_URL=sqlite+aiosqlite:///./vyron.db")
        logger.warning("   Continuing with file-based DB fallback if configured...")
        # Don't exit, try to continue
    else:
        logger.info("✅ Database connected")

    # Init DB tables
    try:
        await init_db()
        logger.info("✅ Database tables ensured")
    except Exception as e:
        logger.error(f"❌ Database init failed: {e}")
        if settings.is_development:
            logger.info("Continuing in development mode...")

    # Seed data
    try:
        from app.database import AsyncSessionLocal
        from sqlalchemy import select, func
        from app.models.models import Game
        from app.seed import seed_all
        
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(func.count(Game.id)))
            count = result.scalar() or 0
            if count == 0:
                logger.info("🌱 Seeding initial data (14 games, products, etc)...")
                await seed_all(db)
                logger.info("✅ Seed completed")
            else:
                logger.info(f"✅ Found {count} games, skipping seed")
    except Exception as e:
        logger.error(f"Seed failed: {e}")

    # Start background tasks
    workers_task = asyncio.create_task(run_background_workers(), name="workers")
    scheduler_task = asyncio.create_task(run_scheduler(), name="scheduler")
    bot_task = asyncio.create_task(start_telegram_bot_task(), name="telegram_bot")

    # Start FastAPI via uvicorn in same loop
    import uvicorn
    from app.main import app as fastapi_app

    config = uvicorn.Config(
        app=fastapi_app,
        host=settings.APP_HOST,
        port=settings.APP_PORT,
        log_level="info" if settings.is_development else "warning",
        access_log=settings.is_development,
        loop="asyncio"
    )
    server = uvicorn.Server(config)

    # Handle shutdown signals
    def signal_handler():
        logger.info("Shutdown signal received")
        shutdown_event.set()
        server.should_exit = True
        workers_task.cancel()
        scheduler_task.cancel()
        bot_task.cancel()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, signal_handler)
        except NotImplementedError:
            # Windows doesn't support add_signal_handler
            pass

    logger.info(f"🚀 Starting FastAPI server on {settings.APP_HOST}:{settings.APP_PORT}")
    logger.info(f"   Public website: {settings.APP_URL}")
    logger.info(f"   API docs: {settings.APP_URL}/docs")
    logger.info(f"   Health: {settings.APP_URL}/health")
    logger.info(f"   Admin: {settings.APP_URL}/admin")
    if settings.TELEGRAM_BOT_TOKEN:
        logger.info(f"   Telegram bot: Enabled")
    else:
        logger.info(f"   Telegram bot: Disabled (no token)")

    logger.info("")
    logger.info("VYRON is ready! Press Ctrl+C to stop.")
    logger.info("")

    try:
        await server.serve()
    except asyncio.CancelledError:
        logger.info("Server cancelled")
    finally:
        logger.info("Shutting down...")
        shutdown_event.set()
        
        # Cancel tasks
        for task in [workers_task, scheduler_task, bot_task]:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        logger.info("✅ VYRON stopped gracefully")

def main():
    """Entry point"""
    # Check .env
    if not os.path.exists(".env"):
        logger.warning("⚠️  .env file not found, using .env.example as reference")
        logger.warning("   Copy .env.example to .env and configure")
        if os.path.exists(".env.example"):
            logger.info("   .env.example exists, you can copy it")

    # Validate critical env
    if len(settings.APP_SECRET) < 16:
        logger.warning("⚠️  APP_SECRET is too short, generate a strong secret!")

    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
