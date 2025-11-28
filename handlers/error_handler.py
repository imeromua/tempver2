# epicservice/handlers/error_handler.py

import logging
import traceback
from typing import Any

from aiogram import Router
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramUnauthorizedError,
)
from aiogram.types import ErrorEvent, Update

from config import ADMIN_IDS

logger = logging.getLogger(__name__)
router = Router()


# ==============================================================================
# 🛡️ ГЛОБАЛЬНИЙ ОБРОБНИК ПОМИЛОК
# ==============================================================================


@router.errors()
async def error_handler(event: ErrorEvent, update: Update) -> Any:
    """
    Глобальний обробник помилок бота.
    Логує всі помилки та надсилає користувачу зрозумілі повідомлення.
    """
    exception = event.exception
    user_id = None

    # Визначаємо user_id з різних типів update
    try:
        if update.message:
            user_id = update.message.from_user.id
        elif update.callback_query:
            user_id = update.callback_query.from_user.id
        elif update.my_chat_member:
            user_id = update.my_chat_member.from_user.id
    except Exception:
        pass

    # Логування помилки
    logger.error(
        "Помилка при обробці update від user_id=%s: %s",
        user_id,
        exception,
        exc_info=True,
    )

    # Детальний traceback для критичних помилок
    if not isinstance(
        exception,
        (
            TelegramBadRequest,
            TelegramNetworkError,
            TelegramForbiddenError,
            TelegramUnauthorizedError,
        ),
    ):
        error_traceback = "".join(
            traceback.format_exception(type(exception), exception, exception.__traceback__)
        )
        logger.critical("Критична помилка:\n%s", error_traceback)

    # Повідомлення користувачу залежно від типу помилки
    user_message = None

    if isinstance(exception, TelegramBadRequest):
        # Неправильний запит до API Telegram
        if "message is not modified" in str(exception).lower():
            # Спроба редагувати повідомлення з тим самим текстом - ігноруємо
            return True
        elif "message to edit not found" in str(exception).lower():
            user_message = "⚠️ Повідомлення застаріло. Спробуйте ще раз."
        elif "query is too old" in str(exception).lower():
            user_message = "⚠️ Запит застарів. Спробуйте ще раз."
        else:
            user_message = "❌ Помилка запиту. Спробуйте інший спосіб."

    elif isinstance(exception, TelegramForbiddenError):
        # Користувач заблокував бота
        logger.info("Користувач %s заблокував бота", user_id)
        return True  # Не надсилаємо повідомлення

    elif isinstance(exception, TelegramUnauthorizedError):
        # Невірний токен бота
        logger.critical("Невірний BOT_TOKEN!")
        return True

    elif isinstance(exception, TelegramNetworkError):
        # Проблеми з мережею
        user_message = "🌐 Проблеми з з'єднанням. Спробуйте пізніше."

    elif isinstance(exception, KeyError):
        # Відсутній ключ (часто в state.data)
        user_message = "❌ Втрачено дані. Почніть операцію заново."
        logger.warning("KeyError для user_id=%s: %s", user_id, exception)

    elif isinstance(exception, ValueError):
        # Невірне значення (конвертація типів тощо)
        user_message = "❌ Невірний формат даних. Перевірте введення."
        logger.warning("ValueError для user_id=%s: %s", user_id, exception)

    elif isinstance(exception, AttributeError):
        # Відсутній атрибут (часто None замість об'єкта)
        user_message = "❌ Помилка обробки даних. Спробуйте ще раз."
        logger.error("AttributeError для user_id=%s: %s", user_id, exception, exc_info=True)

    elif isinstance(exception, IndexError):
        # Вихід за межі списку
        user_message = "❌ Невірний номер позиції."
        logger.warning("IndexError для user_id=%s: %s", user_id, exception)

    else:
        # Невідома помилка
        user_message = (
            "❌ Виникла несподівана помилка.\n"
            "Спробуйте ще раз або зверніться до адміністратора."
        )

    # Надсилаємо повідомлення користувачу
    if user_message and update.message:
        try:
            await update.message.answer(user_message)
        except Exception as send_error:
            logger.error("Не вдалося надіслати повідомлення про помилку: %s", send_error)

    elif user_message and update.callback_query:
        try:
            await update.callback_query.answer(user_message, show_alert=True)
        except Exception as send_error:
            logger.error("Не вдалося показати alert про помилку: %s", send_error)

    # Повідомляємо адмінам про критичні помилки (опціонально)
    if not isinstance(
        exception,
        (
            TelegramBadRequest,
            TelegramNetworkError,
            TelegramForbiddenError,
        ),
    ):
        await notify_admins_about_error(event, user_id, exception)

    return True  # Помилка оброблена, не крашимо бота


# ==============================================================================
# 📢 ПОВІДОМЛЕННЯ АДМІНІВ
# ==============================================================================


async def notify_admins_about_error(event: ErrorEvent, user_id: int, exception: Exception):
    """Повідомляє адміністраторів про критичну помилку."""
    try:
        from aiogram import Bot

        bot: Bot = event.update.bot

        error_text = (
            f"🚨 **Критична помилка в боті!**\n\n"
            f"**User ID:** `{user_id}`\n"
            f"**Тип помилки:** `{type(exception).__name__}`\n"
            f"**Повідомлення:** `{str(exception)[:200]}`\n\n"
            f"Перевірте логи для деталей."
        )

        # Надсилаємо тільки першому адміну, щоб не спамити
        if ADMIN_IDS:
            await bot.send_message(ADMIN_IDS[0], error_text)

    except Exception as notify_error:
        logger.error("Помилка повідомлення адміна про помилку: %s", notify_error)
