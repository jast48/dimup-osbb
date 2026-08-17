import os
import asyncio
import logging
import warnings
import uvicorn
from pathlib import Path

warnings.filterwarnings("ignore", category=FutureWarning)

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from app.config import settings
from app.db.init_db import init_database
from app.webapp.router import router as webapp_router

# Handlers
from app.bot.handlers.start import router as start_router
from app.bot.handlers.tickets import router as tickets_router
from app.bot.handlers.concierge import router as concierge_router
from app.bot.handlers.info import router as info_router
from app.bot.handlers.admin import router as admin_router
from app.bot.handlers.marketplace import router as marketplace_router
from app.bot.handlers.contractor import router as contractor_router
from app.bot.handlers.payments import router as payments_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
)
logger = logging.getLogger("dimup")


def get_dispatcher() -> Dispatcher:
    """Создает диспетчер бота и подключает все хендлеры"""
    dp = Dispatcher()
    dp.include_router(start_router)
    dp.include_router(tickets_router)
    dp.include_router(concierge_router)
    dp.include_router(marketplace_router)
    dp.include_router(contractor_router)
    dp.include_router(payments_router)
    dp.include_router(info_router)
    dp.include_router(admin_router)
    return dp


def create_app() -> FastAPI:
    """Создает и настраивает веб-приложение FastAPI"""
    app = FastAPI(
        title="DimUp Smart OSBB API & WebApp",
        version="1.0.0"
    )

    STATIC_DIR = Path(__file__).resolve().parent / "webapp" / "static"
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    app.include_router(webapp_router)

    # Автоматическое определение публичного HTTPS URL на Render
    render_url = os.getenv("RENDER_EXTERNAL_URL")
    if render_url:
        settings.WEBAPP_URL = f"{render_url.rstrip('/')}/webapp"

    @app.get("/")
    async def root():
        return {
            "system": "DimUp Smart OSBB",
            "status": "online"
        }

    return app


app = create_app()


async def run_services():
    """Асинхронный запуск базы данных, FastAPI сервера и Telegram-бота параллельно"""
    # 1. Инициализируем базу данных
    logger.info("Initializing database...")
    try:
        await init_database()
    except Exception as e:
        logger.error(f"Database initialization error: {e}", exc_info=True)

    # 2. Настраиваем FastAPI сервер для облака (0.0.0.0 и порт Render)
    port = int(os.getenv("PORT", 8000))
    config = uvicorn.Config(app=app, host="0.0.0.0", port=port, log_level="warning")
    server = uvicorn.Server(config)

    # 3. Настраиваем Telegram-бота
    bot = None
    if settings.BOT_TOKEN and ":" in settings.BOT_TOKEN and "YOUR_BOT_TOKEN" not in settings.BOT_TOKEN:
        logger.info("Starting Telegram Bot polling...")
        bot = Bot(token=settings.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        dp = get_dispatcher()

        logger.info("=" * 60)
        logger.info(" DimUp Bot & WebApp successfully started!")
        logger.info(f" WebApp URL: {settings.WEBAPP_URL}")
        logger.info("=" * 60)

        # Запускаем одновременно веб-сервер и polling бота
        try:
            await asyncio.gather(
                server.serve(),
                dp.start_polling(bot, drop_pending_updates=True)
            )
        finally:
            await bot.session.close()
    else:
        logger.warning("BOT_TOKEN is missing or invalid! Starting WebApp only...")
        await server.serve()


def main():
    try:
        asyncio.run(run_services())
    except (KeyboardInterrupt, SystemExit):
        logger.info("DimUp stopped cleanly.")


if __name__ == "__main__":
    main()
