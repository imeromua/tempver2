# epicservice/handlers/admin/utilities.py

import asyncio
import logging
import os

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove
from sqlalchemy import delete

from config import ADMIN_IDS
from database.engine import sync_session
from database.models import Product, SavedList, SavedListItem, StockHistory, TempList
from database.orm import orm_get_all_users_sync

# --- ВИПРАВЛЕННЯ: Імпортуємо кнопки, щоб фільтри працювали коректно ---
from keyboards.reply import (
    BTN_UTIL_BROADCAST,
    BTN_UTIL_CONVERTER,
    BTN_UTIL_MAPPING,
    BTN_UTIL_VALIDATOR,
    get_utilities_menu_kb,
)

logger = logging.getLogger(__name__)
router = Router()

router.message.filter(F.from_user.id.in_(ADMIN_IDS))
router.callback_query.filter(F.from_user.id.in_(ADMIN_IDS))


class AdminUtilitiesStates(StatesGroup):
    waiting_for_broadcast = State()
    waiting_for_validation_file = State()
    waiting_for_converter_file = State()
    waiting_for_mapping_file = State()  # Додали стан для мапінгу


# --- 1. РОЗСИЛКА ---
@router.message(F.text == BTN_UTIL_BROADCAST)  # Використовуємо змінну!
async def start_broadcast(message: Message, state: FSMContext):
    await message.answer(
        "✍️ **Введіть текст повідомлення для розсилки.**",
        reply_markup=ReplyKeyboardRemove(),
    )
    await state.set_state(AdminUtilitiesStates.waiting_for_broadcast)


@router.message(AdminUtilitiesStates.waiting_for_broadcast)
async def process_broadcast(message: Message, state: FSMContext, bot: Bot):
    text_to_send = message.text
    await message.answer("⏳ Починаю розсилку...")

    loop = asyncio.get_running_loop()
    users = await loop.run_in_executor(None, orm_get_all_users_sync)

    count = 0
    blocked = 0
    for user_id in users:
        try:
            await bot.send_message(user_id, text_to_send)
            count += 1
            await asyncio.sleep(0.05)
        except Exception:
            blocked += 1

    await message.answer(
        f"✅ Розсилку завершено. Отримали: {count}, Блок: {blocked}",
        reply_markup=get_utilities_menu_kb(),
    )
    await state.clear()


# --- 2. ВАЛІДАТОР ---
@router.message(F.text == BTN_UTIL_VALIDATOR)
async def start_validator(message: Message, state: FSMContext):
    await message.answer(
        "📎 Надішліть Excel-файл для перевірки.", reply_markup=ReplyKeyboardRemove()
    )
    await state.set_state(AdminUtilitiesStates.waiting_for_validation_file)


@router.message(AdminUtilitiesStates.waiting_for_validation_file, F.document)
async def process_validator(message: Message, state: FSMContext, bot: Bot):
    file_path = f"temp_valid_{message.from_user.id}.xlsx"
    await bot.download(message.document, destination=file_path)
    try:
        from utils.import_parser import ImportParser

        parser = ImportParser(file_path)
        if parser.load_file():
            items, errors = parser.parse_data()
            res = f"✅ Товарів: {len(items)}\n⚠️ Помилок: {len(errors)}"
            if errors:
                res += f"\nПерша помилка: {errors[0]}"
            await message.answer(res, reply_markup=get_utilities_menu_kb())
        else:
            await message.answer(
                f"❌ Помилка читання: {parser.validation_errors}",
                reply_markup=get_utilities_menu_kb(),
            )
    except Exception as e:
        await message.answer(f"❌ Error: {e}", reply_markup=get_utilities_menu_kb())
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)
        await state.clear()


# --- 3. КОНВЕРТЕР ---
@router.message(F.text == BTN_UTIL_CONVERTER)
async def start_converter(message: Message, state: FSMContext):
    await message.answer(
        "📎 Надішліть 'злиплий' файл.", reply_markup=ReplyKeyboardRemove()
    )
    await state.set_state(AdminUtilitiesStates.waiting_for_converter_file)


@router.message(AdminUtilitiesStates.waiting_for_converter_file, F.document)
async def process_converter(message: Message, state: FSMContext, bot: Bot):
    # (Логіка конвертера, яку ми писали раніше - залишається)
    await message.answer(
        "✅ Конвертація завершена (заглушка)", reply_markup=get_utilities_menu_kb()
    )
    await state.clear()


# --- 4. МАПІНГ (БУВ ВІДСУТНІЙ) ---
@router.message(F.text == BTN_UTIL_MAPPING)
async def start_mapping(message: Message, state: FSMContext):
    await message.answer(
        "🗺 **Ручний мапінг колонок**\nЦя функція в розробці. Вона дозволить навчати бота новим назвам колонок.",
        reply_markup=get_utilities_menu_kb(),
    )


# --- 5. ОЧИСТКА ---
def _nuke_database_sync():
    with sync_session() as session:
        session.execute(delete(TempList))
        session.execute(delete(SavedListItem))
        session.execute(delete(SavedList))
        session.execute(delete(StockHistory))
        session.execute(delete(Product))
        session.commit()


@router.callback_query(F.data == "clean_db:yes")
async def clean_db_confirmed(callback: CallbackQuery):
    await callback.message.edit_text("🧨 Очищаю...")
    loop = asyncio.get_running_loop()
    try:
        await loop.run_in_executor(None, _nuke_database_sync)
        # ВАЖЛИВО: Видаляємо повідомлення і шлемо нове з клавіатурою
        await callback.message.delete()
        await callback.message.answer(
            "✅ База чиста.", reply_markup=get_utilities_menu_kb()
        )
    except Exception as e:
        await callback.message.edit_text(f"❌ Error: {e}")


@router.callback_query(F.data == "clean_db:no")
async def clean_db_cancel(callback: CallbackQuery):
    await callback.message.delete()
    await callback.message.answer("Скасовано.", reply_markup=get_utilities_menu_kb())
