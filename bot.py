# epicservice/bot.py

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from sqlalchemy import text

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


async def set_main_menu(bot: Bot):
    """
    Очищує стандартне меню команд, оскільки використовуємо Reply-клавіатуру.
    """
    await bot.set_my_commands([])


async def main():
    """
    Головна асинхронна функція для ініціалізації та запуску бота.
    """
    # Налаштування логування
    log_format = (
        "%(asctime)s - %(levelname)s - "
        "[User:%(user_id)s | Update:%(update_id)s] - "
        "%(name)s - %(message)s"
    )
    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("bot.log", mode="a"),
        ],
    )
    logger = logging.getLogger(__name__)

    if not BOT_TOKEN:
        logger.critical(
            "Критична помилка: BOT_TOKEN не знайдено! Перевірте ваш .env файл."
        )
        sys.exit(1)

    # Перевірка БД
    try:
        async with async_session() as session:
            await session.execute(text("SELECT 1"))
        logger.info("Підключення до бази даних успішне.")
    except Exception as e:
        logger.critical("Помилка підключення до бази даних: %s", e, exc_info=True)
        sys.exit(1)

    # Ініціалізація бота
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(
            parse_mode="Markdown", link_preview_is_disabled=True
        ),
    )
    dp = Dispatcher()

    # --- MIDDLEWARES ---
    dp.update.middleware(LoggingMiddleware())
    dp.message.middleware(ThrottlingMiddleware(rate_limit=0.5))
    dp.callback_query.middleware(ThrottlingMiddleware(rate_limit=0.5))

    # --- РЕЄСТРАЦІЯ РОУТЕРІВ (ПОРЯДОК ВАЖЛИВИЙ!) ---

    # 1. Перехоплення помилок (має бути першим)
    dp.include_router(error_handler.router)

    # 2. Навігація меню (Reply-кнопки головного меню та підменю)
    dp.include_router(menu_navigation.router)

    # 3. Адмінські модулі
    dp.include_router(admin_core.router)
    dp.include_router(admin_import.router)
    dp.include_router(admin_reports.router)
    dp.include_router(admin_archive.router)
    dp.include_router(admin_backups.router)
    dp.include_router(admin_exports.router)
    dp.include_router(admin_utilities.router)

    # 4. Користувацькі модулі
    dp.include_router(list_management.router)
    dp.include_router(list_editing.router)  # Редагування списку (Reply)
    dp.include_router(item_addition.router)  # Додавання товарів (Reply)
    dp.include_router(list_saving.router)
    dp.include_router(archive.router)

    # 5. Загальні команди (/start, /help)
    dp.include_router(common.router)

    # 6. Пошук товарів (ОСТАННІЙ! Ловить весь текст)
    # Цей роутер має бути останнім, бо він обробляє F.text без додаткових фільтрів
    dp.include_router(user_search.router)

    try:
        await set_main_menu(bot)
        await bot.delete_webhook(drop_pending_updates=True)

        logger.info("🚀 Бот запускається...")
        logger.info("✅ Міграція на Reply клавіатури завершена")
        logger.info("📋 Всі inline клавіатури замінені на Reply")
        await dp.start_polling(bot)

    except Exception as e:
        logger.critical("Критична помилка під час роботи бота: %s", e, exc_info=True)
    finally:
        logger.info("Завершення роботи бота...")
        await bot.session.close()
        logger.info("Сесія бота закрита.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Бот зупинено користувачем.")
    except Exception as e:
        logging.critical("Неочікувана помилка на верхньому рівні: %s", e, exc_info=True)
        sys.exit(1)
