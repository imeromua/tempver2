# epicservice/handlers/admin/core.py

import asyncio
import logging
from typing import Union

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from config import ADMIN_IDS
from handlers.common import clean_previous_keyboard
# Імпортуємо нові клавіатури
from keyboards.inline import (
    get_admin_panel_kb, 
    get_exports_menu_kb, 
    get_reports_menu_kb
)
from lexicon.lexicon import LEXICON

logger = logging.getLogger(__name__)
router = Router()
router.message.filter(F.from_user.id.in_(ADMIN_IDS))
router.callback_query.filter(F.from_user.id.in_(ADMIN_IDS))

async def _show_admin_panel(event: Union[Message, CallbackQuery], state: FSMContext, bot: Bot):
    """Відображає головне меню адмін-панелі."""
    text = LEXICON.ADMIN_PANEL_GREETING
    reply_markup = get_admin_panel_kb()

    if isinstance(event, Message):
        await clean_previous_keyboard(state, bot, event.chat.id)
        sent_message = await event.answer(text, reply_markup=reply_markup)
        await state.update_data(main_message_id=sent_message.message_id)
    
    elif isinstance(event, CallbackQuery):
        try:
            await event.message.edit_text(text, reply_markup=reply_markup)
            await state.update_data(main_message_id=event.message.message_id)
        except TelegramBadRequest:
            await clean_previous_keyboard(state, bot, event.message.chat.id)
            sent_message = await event.message.answer(text, reply_markup=reply_markup)
            await state.update_data(main_message_id=sent_message.message_id)

@router.message(F.text == "👑 Адмін-панель")
async def admin_panel_handler(message: Message, state: FSMContext, bot: Bot):
    await _show_admin_panel(message, state, bot)

@router.callback_query(F.data == "admin:main")
async def admin_panel_callback_handler(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await state.set_state(None)
    await _show_admin_panel(callback, state, bot)
    await callback.answer()

# --- Навігація по підменю ---

@router.callback_query(F.data == "admin:exports_menu")
async def show_exports_menu(callback: CallbackQuery):
    await callback.message.edit_text(LEXICON.EXPORTS_TITLE, reply_markup=get_exports_menu_kb())

@router.callback_query(F.data == "admin:reports_menu")
async def show_reports_menu(callback: CallbackQuery):
    await callback.message.edit_text(LEXICON.REPORTS_TITLE, reply_markup=get_reports_menu_kb())

@router.callback_query(F.data == "admin:users_menu")
async def show_users_menu(callback: CallbackQuery):
    await callback.answer("Цей розділ в розробці 🛠", show_alert=True)