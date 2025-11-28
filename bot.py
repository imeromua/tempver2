# epicservice/bot.py

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from sqlalchemy import text
from apscheduler.schedulers.asyncio import AsyncIOScheduler # 👇 Додано

from config import BOT_TOKEN
from database.engine import async_session

# --- ІМПОРТИ РОУТЕРІВ ---
from handlers import archive, common, error_handler, menu_navigation, user_search
from handlers.admin import archive_handlers as admin_archive
from handlers.admin import backup_handlers as admin_backups
from handlers.admin import core as admin_core
from handlers.admin import export_handlers as admin_exports
from handlers.admin import import_handlers as admin_import
from handlers.admin import report_handlers as admin_reports
from handlers.admin import utilities as admin_utilities
from handlers.user import item_addition, list_editing, list_management, list_saving
from middlewares.logging_middleware import LoggingMiddleware
from middlewares.throttling import ThrottlingMiddleware

# 👇 Імпорт сервісу пошти
from services.email_listener import EmailService

async def set_main_menu(bot: Bot):
    await bot.set_my_commands([])

async def main():
    log_format = "%(asctime)s - %(levelname)s - %(name)s - %(message)s"
    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler("bot.log", mode="a")],
    )
    logger = logging.getLogger(__name__)

    if not BOT_TOKEN:
        sys.exit(1)

    # Перевірка БД
    try:
        async with async_session() as session:
            await session.execute(text("SELECT 1"))
        logger.info("Підключення до бази даних успішне.")
    except Exception as e:
        logger.critical("Помилка підключення до БД: %s", e)
        sys.exit(1)

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="Markdown", link_preview_is_disabled=True))
    dp = Dispatcher()

    dp.update.middleware(LoggingMiddleware())
    dp.message.middleware(ThrottlingMiddleware(rate_limit=0.5))
    dp.callback_query.middleware(ThrottlingMiddleware(rate_limit=0.5))

    # --- РЕЄСТРАЦІЯ РОУТЕРІВ ---
    dp.include_router(error_handler.router)
    dp.include_router(menu_navigation.router)
    dp.include_router(admin_core.router)
    dp.include_router(admin_import.router)
    dp.include_router(admin_reports.router)
    dp.include_router(admin_archive.router)
    dp.include_router(admin_backups.router)
    dp.include_router(admin_exports.router)
    dp.include_router(admin_utilities.router)
    dp.include_router(list_management.router)
    dp.include_router(list_editing.router)
    dp.include_router(item_addition.router)
    dp.include_router(list_saving.router)
    dp.include_router(archive.router)
    dp.include_router(common.router)
    dp.include_router(user_search.router)

    # --- 📧 ЗАПУСК EMAIL СЕРВІСУ ---
    email_service = EmailService(bot)
    scheduler = AsyncIOScheduler()
    # Перевіряємо пошту кожні 5 хвилин
    scheduler.add_job(email_service.check_email_and_process, "interval", minutes=5)
    scheduler.start()
    logger.info("📧 Email Listener запущено (інтервал: 5 хв)")

    try:
        await set_main_menu(bot)
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("🚀 Бот запускається...")
        await dp.start_polling(bot)
    except Exception as e:
        logger.critical("Критична помилка: %s", e, exc_info=True)
    finally:
        logger.info("Завершення роботи бота...")
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass