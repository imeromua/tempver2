# epicservice/handlers/common.py

import logging

from aiogram import Bot, F, Router  # <--- Додав F сюди
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message  # <--- Додав CallbackQuery

from config import ADMIN_IDS
from database.orm import orm_upsert_user

# Використовуємо НОВУ клавіатуру
from keyboards.reply import get_main_menu_kb

logger = logging.getLogger(__name__)

router = Router()


async def clean_previous_keyboard(state: FSMContext, bot: Bot, chat_id: int):
    """
    Допоміжна функція для видалення клавіатури з попереднього повідомлення.
    Вона потрібна для сумісності зі старими хендлерами, які використовують Inline-кнопки.
    """
    data = await state.get_data()
    previous_message_id = data.get("main_message_id")
    if previous_message_id:
        try:
            await bot.edit_message_reply_markup(
                chat_id=chat_id, message_id=previous_message_id, reply_markup=None
            )
        except TelegramBadRequest as e:
            # Це нормально, якщо повідомлення вже видалено або не може бути змінено
            logger.debug("Не вдалося видалити клавіатуру: %s", e)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, bot: Bot):
    """
    Обробник команди /start.
    Ініціалізує користувача і видає головне Reply-меню.
    """
    user = message.from_user
    try:
        # Реєструємо або оновлюємо юзера в БД
        await orm_upsert_user(
            user_id=user.id, username=user.username, first_name=user.first_name
        )
        logger.info("Обробка команди /start для користувача %s.", user.id)

        # Перевіряємо права адміна
        is_admin = user.id in ADMIN_IDS

        # Очищуємо будь-який попередній стан діалогу
        await state.clear()

        # Надсилаємо привітання та нову клавіатуру
        await message.answer(
            "👋 **Вітаю в Епік-сервіс!**\n\n"
            "Я допоможу вам працювати зі складом.\n"
            "Оберіть дію в меню знизу 👇",
            reply_markup=get_main_menu_kb(is_admin=is_admin),
        )

    except Exception as e:
        logger.error(
            "Неочікувана помилка в cmd_start для %s: %s", user.id, e, exc_info=True
        )
        await message.answer("😔 Сталася помилка при запуску.")


@router.callback_query(F.data == "card:close")
async def close_card_handler(callback: CallbackQuery):
    """Обробник закриття (видалення) картки товару."""
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.answer()
