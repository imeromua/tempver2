# epicservice/handlers/admin/core.py

import logging
from typing import Union

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from config import ADMIN_IDS

# Використовуємо НОВУ клавіатуру (Reply)
from keyboards.reply import get_admin_menu_kb

logger = logging.getLogger(__name__)
router = Router()

# Фільтруємо тільки адмінів
router.message.filter(F.from_user.id.in_(ADMIN_IDS))
router.callback_query.filter(F.from_user.id.in_(ADMIN_IDS))


async def _show_admin_panel(
    event: Union[Message, CallbackQuery], state: FSMContext, bot: Bot
):
    """
    Універсальна функція для показу адмін-панелі (Reply меню).
    Використовується в інших хендлерах для повернення в меню.
    """
    text = "👑 **Адмін-панель**"
    kb = get_admin_menu_kb()

    if isinstance(event, Message):
        await event.answer(text, reply_markup=kb)

    elif isinstance(event, CallbackQuery):
        # Якщо ми прийшли з інлайн-кнопки, старе повідомлення краще видалити,
        # щоб не засмічувати чат, і надіслати нове з меню знизу.
        try:
            await event.message.delete()
        except Exception:
            pass
        await event.message.answer(text, reply_markup=kb)


# --- Хендлери ---


@router.message(F.text == "👑 Адмін-панель")
async def admin_panel_handler(message: Message, state: FSMContext, bot: Bot):
    await _show_admin_panel(message, state, bot)


@router.callback_query(F.data == "admin:main")
async def admin_panel_callback_handler(
    callback: CallbackQuery, state: FSMContext, bot: Bot
):
    """Обробляє натискання інлайн-кнопки 'Назад в меню'."""
    await state.set_state(None)
    await _show_admin_panel(callback, state, bot)
    await callback.answer()


# Старі хендлери для експортів/звітів (inline) видалені,
# оскільки тепер це робиться через menu_navigation.py
