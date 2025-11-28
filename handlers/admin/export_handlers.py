# epicservice/handlers/admin/export_handlers.py

import asyncio
import logging
import os
from functools import partial  # <--- ДОДАНО для передачі аргументів

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile

from config import ADMIN_IDS
from database.orm.analytics import (
    get_collected_history_dataframe,
    get_products_dataframe,
    get_stock_history_dataframe,
)
from handlers.admin.core import _show_admin_panel
from utils.excel_renderer import save_dataframe_to_excel

logger = logging.getLogger(__name__)
router = Router()
router.callback_query.filter(F.from_user.id.in_(ADMIN_IDS))


async def _generate_and_send_report(
    callback: CallbackQuery,
    state: FSMContext,  # <--- ДОДАНО state
    data_getter_func,
    file_prefix: str,
    caption: str,
    bot: Bot,
    **kwargs,
):
    """Універсальна функція для генерації та відправки звіту."""
    await callback.message.edit_text(f"⏳ Генерую звіт: {caption}...")

    loop = asyncio.get_running_loop()

    # --- ВИПРАВЛЕННЯ 1: Використовуємо partial для передачі kwargs ---
    func = partial(data_getter_func, **kwargs)

    try:
        # Запускаємо синхронну функцію в окремому потоці
        df = await loop.run_in_executor(None, func)

        if df.empty:
            await callback.message.edit_text("📂 Даних для звіту не знайдено.")
            await asyncio.sleep(2)
            # --- ВИПРАВЛЕННЯ 2: Передаємо реальний state ---
            await _show_admin_panel(callback, state, bot)
            return

        # Зберігаємо файл
        file_path = await loop.run_in_executor(
            None, save_dataframe_to_excel, df, file_prefix
        )

        if file_path:
            # Відправляємо файл
            await callback.message.answer_document(
                FSInputFile(file_path), caption=f"✅ {caption}"
            )
            # Видаляємо тимчасовий файл
            os.remove(file_path)

            # Видаляємо повідомлення "Генерую..." і показуємо меню
            await callback.message.delete()
            await _show_admin_panel(callback, state, bot)
        else:
            await callback.message.edit_text("❌ Помилка створення файлу.")
            await asyncio.sleep(2)
            await _show_admin_panel(callback, state, bot)

    except Exception as e:
        logger.error(f"Export error: {e}", exc_info=True)
        await callback.message.edit_text(f"❌ Сталася помилка: {e}")
        await asyncio.sleep(3)
        await _show_admin_panel(callback, state, bot)


# --- Обробники кнопок (Тепер всі приймають state) ---


@router.callback_query(F.data == "export:db_full")
async def export_db_full(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await _generate_and_send_report(
        callback,
        state,
        get_products_dataframe,
        "db_full",
        "Вся база товарів",
        bot,
        filter_type="all",
    )


@router.callback_query(F.data == "export:db_active")
async def export_db_active(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await _generate_and_send_report(
        callback,
        state,
        get_products_dataframe,
        "db_active",
        "Тільки активні товари",
        bot,
        filter_type="active",
    )


@router.callback_query(F.data == "export:no_move")
async def export_no_move(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await _generate_and_send_report(
        callback,
        state,
        get_products_dataframe,
        "db_stagnant",
        "Товари без руху (3+ міс)",
        bot,
        filter_type="no_move",
    )


@router.callback_query(F.data == "export:collected")
async def export_collected(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await _generate_and_send_report(
        callback,
        state,
        get_collected_history_dataframe,
        "collected_history",
        "Історія зборів",
        bot,
    )


@router.callback_query(F.data == "export:history")
async def export_history(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await _generate_and_send_report(
        callback,
        state,
        get_stock_history_dataframe,
        "stock_changes",
        "Історія змін залишків",
        bot,
    )
