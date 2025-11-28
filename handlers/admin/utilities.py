# epicservice/handlers/admin/utilities.py

import asyncio
import logging
import os
import pandas as pd

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.exceptions import TelegramRetryAfter
from sqlalchemy import select

from config import ADMIN_IDS, ARCHIVES_PATH
from database.engine import async_session
from database.models import User
# 👇 Імпортуємо константи кнопок!
from keyboards.reply import (
    get_utilities_menu_kb, 
    get_admin_menu_kb,
    BTN_UTIL_BROADCAST,
    BTN_UTIL_VALIDATOR,
    BTN_UTIL_CONVERTER,
    BTN_UTIL_CLEAN_DB
)
from keyboards.inline import get_yes_no_kb
from utils.import_processor import process_import_dataframe, generate_import_preview, read_excel_smart, detect_columns

logger = logging.getLogger(__name__)
router = Router()

class UtilityStates(StatesGroup):
    waiting_broadcast_message = State()
    waiting_file_validate = State()
    resolving_columns = State()
    waiting_file_convert = State()

# ==============================================================================
# 📢 РОЗСИЛКА
# ==============================================================================

# Використовуємо константу BTN_UTIL_BROADCAST
@router.message(F.text == BTN_UTIL_BROADCAST)
async def start_broadcast(message: Message, state: FSMContext):
    """Запускає процес розсилки."""
    if message.from_user.id not in ADMIN_IDS: return
    await state.set_state(UtilityStates.waiting_broadcast_message)
    await message.answer(
        "📢 **Розсилка повідомлень**\n\n"
        "Надішліть текст, який отримають всі користувачі бота."
    )

@router.message(UtilityStates.waiting_broadcast_message)
async def process_broadcast(message: Message, state: FSMContext):
    """Отримує текст і запитує підтвердження Inline."""
    if message.from_user.id not in ADMIN_IDS: return
    
    await state.update_data(broadcast_text=message.text)
    
    await message.answer(
        f"📢 **Текст для розсилки:**\n\n{message.text[:500]}...\n\n"
        f"⚠️ Надіслати всім користувачам?",
        reply_markup=get_yes_no_kb("broadcast")
    )

@router.callback_query(UtilityStates.waiting_broadcast_message, F.data == "confirm:broadcast:yes")
async def confirm_broadcast(callback: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    text = data.get("broadcast_text")
    
    await callback.message.delete()
    msg = await callback.message.answer("⏳ Розсилка розпочата...")
    
    success = 0
    blocked = 0
    error = 0
    
    try:
        async with async_session() as session:
            result = await session.execute(select(User))
            users = result.scalars().all()
        
        for user in users:
            try:
                await bot.send_message(user.id, text)
                success += 1
                await asyncio.sleep(0.05)
            except TelegramRetryAfter as e:
                await asyncio.sleep(e.retry_after)
                try:
                    await bot.send_message(user.id, text)
                    success += 1
                except: error += 1
            except Exception as e:
                if "blocked" in str(e).lower():
                    blocked += 1
                else:
                    error += 1
        
        await msg.edit_text(
            f"✅ **Розсилка завершена!**\n\n"
            f"📨 Надіслано: {success}\n"
            f"🚫 Заблоковано: {blocked}\n"
            f"❌ Помилок: {error}"
        )
    except Exception as e:
        logger.error("Broadcast error: %s", e)
        await msg.edit_text(f"❌ Помилка: {e}")
    finally:
        await state.clear()
        await callback.answer()

@router.callback_query(UtilityStates.waiting_broadcast_message, F.data == "confirm:broadcast:no")
async def cancel_broadcast(callback: CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await callback.message.answer("❌ Розсилка скасована.", reply_markup=get_utilities_menu_kb())
    await state.clear()
    await callback.answer()

# ==============================================================================
# ✅ ВАЛІДАТОР ФАЙЛІВ
# ==============================================================================

@router.message(F.text == BTN_UTIL_VALIDATOR)
async def validate_file_start(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS: return
    await state.set_state(UtilityStates.waiting_file_validate)
    await message.answer("✅ **Валідатор файлів**\nНадішліть Excel файл для аналізу.")

@router.message(UtilityStates.waiting_file_validate, F.document)
async def validate_file_process(message: Message, state: FSMContext, bot: Bot):
    if message.from_user.id not in ADMIN_IDS: return
    
    document = message.document
    msg = await message.answer("⏳ Розумний аналіз файлу...")
    file_path = os.path.join(ARCHIVES_PATH, f"val_{document.file_name}")
    os.makedirs(ARCHIVES_PATH, exist_ok=True)

    try:
        file = await bot.get_file(document.file_id)
        await bot.download_file(file.file_path, file_path)

        loop = asyncio.get_running_loop()
        # Розумне читання
        df, header_row = await loop.run_in_executor(None, read_excel_smart, file_path)
        detected_map, unknown_cols = detect_columns(df)
        
        # Використовуємо process_import_dataframe для перевірки даних
        processed_df, validation = await loop.run_in_executor(
            None, process_import_dataframe, df, None
        )

        result_text = f"📄 Файл: `{document.file_name}`\n"
        result_text += f"📌 Заголовок: рядок {header_row + 1}\n"
        result_text += f"📊 Всього рядків: {len(df)}\n"
        
        if validation.is_valid:
            result_text += "✅ **Файл ПІДХОДИТЬ!**\n"
            result_text += f"✔️ Готових: {validation.valid_rows}\n"
        else:
            result_text += "❌ **Файл НЕ ПІДХОДИТЬ!**\n"
            result_text += f"⚠️ Помилок: {len(validation.errors)}\n"
            if validation.errors:
                result_text += "Приклад помилки: " + validation.errors[0] + "\n"

        # Колонки
        result_text += "\n🔍 Колонки:\n"
        for col, det in detected_map.items():
             emoji = "✅" if det else "❌"
             result_text += f"{emoji} {col}: {det or '-'}\n"
             
        if unknown_cols:
            result_text += f"\n❓ Невідомі ({len(unknown_cols)}): {', '.join(unknown_cols[:3])}..."

        await msg.edit_text(result_text)
        
    except Exception as e:
        await msg.edit_text(f"❌ Помилка обробки: {e}")
    finally:
        if os.path.exists(file_path): os.remove(file_path)
        await state.clear()

# ==============================================================================
# 🔄 КОНВЕРТЕР (РОЗДІЛЕННЯ КОЛОНОК)
# ==============================================================================

@router.message(F.text == BTN_UTIL_CONVERTER)
async def converter_start(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS: return
    await state.set_state(UtilityStates.waiting_file_convert)
    await message.answer(
        "🔄 **Конвертер таблиць**\n"
        "Надішліть файл, де Артикул і Назва злиті.\n"
        "Я розділю їх і надішлю файл назад."
    )

@router.message(UtilityStates.waiting_file_convert, F.document)
async def converter_process(message: Message, state: FSMContext, bot: Bot):
    if message.from_user.id not in ADMIN_IDS: return
    
    document = message.document
    msg = await message.answer("⏳ Обробка...")
    file_path = os.path.join(ARCHIVES_PATH, f"conv_{document.file_name}")
    out_path = os.path.join(ARCHIVES_PATH, f"converted_{document.file_name}")
    os.makedirs(ARCHIVES_PATH, exist_ok=True)

    try:
        file = await bot.get_file(document.file_id)
        await bot.download_file(file.file_path, file_path)

        loop = asyncio.get_running_loop()
        df, _ = await loop.run_in_executor(None, read_excel_smart, file_path)
        
        # Обробка
        processed_df, _ = await loop.run_in_executor(
            None, process_import_dataframe, df, None
        )
        
        if processed_df.empty:
            await msg.edit_text("❌ Не вдалося конвертувати.")
            return

        await loop.run_in_executor(None, lambda: processed_df.to_excel(out_path, index=False))
        
        await msg.delete()
        await message.answer_document(
            FSInputFile(out_path),
            caption="✅ **Файл конвертовано!**"
        )

    except Exception as e:
        await msg.edit_text(f"❌ Помилка: {e}")
    finally:
        if os.path.exists(file_path): os.remove(file_path)
        if os.path.exists(out_path): os.remove(out_path)
        await state.clear()

# ==============================================================================
# 🧨 ОЧИСТКА БД
# ==============================================================================

@router.message(F.text == BTN_UTIL_CLEAN_DB)
async def util_clean_db_trigger(message: Message):
    if message.from_user.id not in ADMIN_IDS: return
    
    await message.answer(
        "🧨 **ПОВНА ОЧИСТКА БД**\nAre you sure?",
        reply_markup=get_yes_no_kb("clean_db")
    )

@router.callback_query(F.data == "confirm:clean_db:yes")
async def confirm_clean_db(callback: CallbackQuery):
    await callback.message.delete()
    # TODO: Реалізувати очищення
    await callback.message.answer("✅ База даних очищена (заглушка).")
    await callback.answer()

@router.callback_query(F.data == "confirm:clean_db:no")
async def cancel_clean_db(callback: CallbackQuery):
    await callback.message.delete()
    await callback.message.answer("❌ Очистка скасована.")
    await callback.answer()