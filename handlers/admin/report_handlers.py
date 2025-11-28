# epicservice/handlers/admin/report_handlers.py

import asyncio
import logging
import os
from datetime import datetime
from typing import Optional

import pandas as pd
from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from config import ADMIN_IDS, ARCHIVES_PATH
from database.orm import (
    orm_get_all_products_sync,
    orm_get_all_temp_list_items_sync,
    orm_subtract_collected,
)
from keyboards.reply import get_admin_menu_kb  # <--- Нова клавіатура

logger = logging.getLogger(__name__)

router = Router()
router.message.filter(F.from_user.id.in_(ADMIN_IDS))


# Стан для завантаження файлу "віднімання"
class AdminReportStates(StatesGroup):
    waiting_for_subtract_file = State()


# --- ДОПОМІЖНІ ФУНКЦІЇ (Використовуються також в menu_navigation) ---


def _create_stock_report_sync() -> Optional[str]:
    """
    Генерує Excel-файл із поточними залишками (включно з резервами).
    """
    try:
        products = orm_get_all_products_sync()
        temp_list_items = orm_get_all_temp_list_items_sync()

        # Рахуємо тимчасові резерви "на льоту"
        temp_reservations = {}
        for item in temp_list_items:
            temp_reservations[item.product_id] = (
                temp_reservations.get(item.product_id, 0) + item.quantity
            )

        report_data = []
        for product in products:
            try:
                stock_qty = float(str(product.кількість).replace(",", "."))
            except (ValueError, TypeError):
                stock_qty = 0

            # Резерв = Постійний (в базі) + Тимчасовий (у кошиках юзерів)
            reserved = (product.відкладено or 0) + temp_reservations.get(product.id, 0)
            available = stock_qty - reserved

            # У звіті показуємо тільки реальні цифри
            report_data.append(
                {
                    "Відділ": product.відділ,
                    "Група": product.група,
                    "Артикул": product.артикул,
                    "Назва": product.назва,
                    "Всього на складі": stock_qty,
                    "В резерві": reserved,
                    "Доступно": available,
                    "Ціна": product.ціна or 0.0,
                    "Сума (Доступно)": available * (product.ціна or 0.0),
                }
            )

        df = pd.DataFrame(report_data)
        os.makedirs(ARCHIVES_PATH, exist_ok=True)
        report_path = os.path.join(
            ARCHIVES_PATH, f"stock_report_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
        )
        df.to_excel(report_path, index=False)
        return report_path
    except Exception as e:
        logger.error("Помилка створення звіту про залишки: %s", e, exc_info=True)
        return None


def _parse_and_validate_subtract_file(df: pd.DataFrame) -> Optional[pd.DataFrame]:
    """
    Валідує та нормалізує файл для віднімання залишків.
    Шукає колонки 'Артикул' та 'Кількість'.
    """
    try:
        # 1. Приводимо заголовки до нижнього регістру
        df.columns = [str(c).lower().strip() for c in df.columns]

        # 2. Шукаємо ключові слова
        col_map = {}
        for col in df.columns:
            if col in ["артикул", "art", "code", "sku"]:
                col_map["article"] = col
            elif col in ["кількість", "qty", "count", "k"]:
                col_map["qty"] = col

        # Якщо знайшли явні колонки
        if "article" in col_map and "qty" in col_map:
            df_prepared = df[[col_map["article"], col_map["qty"]]].copy()
            df_prepared.columns = ["артикул", "кількість"]
            # Чистимо артикули
            df_prepared["артикул"] = (
                df_prepared["артикул"].astype(str).str.replace(r"\.0$", "", regex=True)
            )
            return df_prepared

        # 3. Якщо колонок немає, але їх всього 2 - припускаємо, що це [Артикул, Кількість]
        if len(df.columns) == 2:
            # Створюємо новий DF, де перший рядок (header) стає даними, якщо там цифри
            # Але простіше просто перейменувати
            df.columns = ["артикул", "кількість"]
            df["артикул"] = (
                df["артикул"].astype(str).str.replace(r"\.0$", "", regex=True)
            )
            return df

    except Exception as e:
        logger.error(f"Помилка парсингу файлу для віднімання: {e}")

    return None


# --- ОБРОБНИК ФАЙЛУ (Triggered by state from menu_navigation) ---


@router.message(AdminReportStates.waiting_for_subtract_file, F.document)
async def process_subtract_file(message: Message, state: FSMContext, bot: Bot):
    """
    Приймає файл "Імпорт зібраного" та віднімає ці кількості від складу.
    """
    await message.answer("⏳ Обробляю файл списання...")

    # Видаляємо попереднє повідомлення, якщо його ID збережено (не обов'язково, але чисто)
    data = await state.get_data()
    if msg_id := data.get("main_message_id"):
        try:
            await bot.delete_message(message.chat.id, msg_id)
        except Exception:
            pass

    await state.clear()

    temp_file_path = f"temp_subtract_{message.from_user.id}.xlsx"

    try:
        await bot.download(message.document, destination=temp_file_path)

        # Читаємо Excel
        df = await asyncio.to_thread(pd.read_excel, temp_file_path)

        # Валідуємо
        standardized_df = _parse_and_validate_subtract_file(df)

        if standardized_df is None:
            await message.answer(
                "❌ **Помилка формату!**\n"
                "Файл повинен мати 2 колонки: `Артикул` та `Кількість`.",
                reply_markup=get_admin_menu_kb(),
            )
        else:
            # Виконуємо віднімання (ORM)
            result = await orm_subtract_collected(standardized_df)

            report_text = (
                "✅ **Списання завершено!**\n"
                "━━━━━━━━━━━━━━━━\n"
                f"📉 Опрацьовано: {result['processed']}\n"
                f"❓ Не знайдено: {result['not_found']}\n"
                f"⚠️ Помилки: {result['errors']}"
            )
            await message.answer(report_text, reply_markup=get_admin_menu_kb())

    except Exception as e:
        logger.error("Critical subtract error: %s", e, exc_info=True)
        await message.answer(
            f"❌ Критична помилка: {e}", reply_markup=get_admin_menu_kb()
        )
    finally:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
