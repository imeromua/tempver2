# epicservice/handlers/admin/export_handlers.py

import asyncio
import logging
import os
from datetime import datetime

import pandas as pd
from aiogram import F, Router
from aiogram.types import FSInputFile, Message

from config import ADMIN_IDS, ARCHIVES_PATH
from database.orm.analytics import (
    orm_get_all_collected_items_sync,
    orm_get_department_stats,
    orm_get_general_stats,
)
from handlers.admin.report_handlers import _create_stock_report_sync

logger = logging.getLogger(__name__)
router = Router()


# ==============================================================================
# 📤 ЕКСПОРТ ЗАЛИШКІВ
# ==============================================================================


@router.message(F.text == "📤 Експорт залишків")
async def export_stock(message: Message):
    """Експортує поточні залишки складу в Excel."""
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("🚫 У вас немає доступу до цієї функції.")
        return

    await message.answer("📤 Формую звіт по залишках...")

    try:
        loop = asyncio.get_running_loop()
        report_path = await loop.run_in_executor(None, _create_stock_report_sync)

        if report_path and os.path.exists(report_path):
            await message.answer_document(
                FSInputFile(report_path),
                caption=f"📊 **Звіт по залишках**\n📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}",
            )

            # Видаляємо файл після відправки
            os.remove(report_path)
        else:
            await message.answer("❌ Помилка створення звіту. Можливо, немає товарів.")

    except Exception as e:
        logger.error("Помилка експорту залишків: %s", e, exc_info=True)
        await message.answer(f"❌ Помилка експорту:\n{str(e)}")


# ==============================================================================
# 📋 ЕКСПОРТ ЗІБРАНОГО
# ==============================================================================


@router.message(F.text == "📋 Експорт зібраного")
async def export_collected(message: Message):
    """Експортує всі зібрані товари з усіх збережених списків."""
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("🚫 У вас немає доступу до цієї функції.")
        return

    await message.answer("📋 Формую звіт по зібраному...")

    try:
        loop = asyncio.get_running_loop()
        items = await loop.run_in_executor(None, orm_get_all_collected_items_sync)

        if not items:
            await message.answer("📭 Зібраних товарів ще немає.")
            return

        # Формуємо DataFrame
        df = pd.DataFrame(items)

        # Перейменовуємо колонки для зручності
        column_mapping = {
            "article": "Артикул",
            "name": "Назва",
            "quantity": "Кількість",
            "user_id": "User ID",
            "created_at": "Дата",
        }
        df = df.rename(columns=column_mapping)

        # Форматуємо дату
        if "Дата" in df.columns:
            df["Дата"] = pd.to_datetime(df["Дата"]).dt.strftime("%d.%m.%Y %H:%M")

        # Створюємо файл
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"collected_report_{timestamp}.xlsx"
        filepath = os.path.join(ARCHIVES_PATH, filename)
        os.makedirs(ARCHIVES_PATH, exist_ok=True)

        await loop.run_in_executor(
            None, lambda: df.to_excel(filepath, index=False, engine="openpyxl")
        )

        # Відправляємо файл
        await message.answer_document(
            FSInputFile(filepath),
            caption=f"📋 **Звіт по зібраним товарам**\n📊 Всього позицій: {len(items)}",
        )

        # Видаляємо файл
        os.remove(filepath)

        logger.info("Експортовано зібрані товари: %s позицій", len(items))

    except Exception as e:
        logger.error("Помилка експорту зібраного: %s", e, exc_info=True)
        await message.answer(f"❌ Помилка експорту:\n{str(e)}")


# ==============================================================================
# 📊 ЕКСПОРТ СТАТИСТИКИ
# ==============================================================================


@router.message(F.text == "📊 Експорт статистики")
async def export_statistics(message: Message):
    """Експортує загальну статистику по системі."""
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("🚫 У вас немає доступу до цієї функції.")
        return

    await message.answer("📊 Формую статистику...")

    try:
        loop = asyncio.get_running_loop()

        # Отримуємо загальну статистику
        general_stats = await loop.run_in_executor(None, orm_get_general_stats)

        # Статистика по відділам
        department_stats = await loop.run_in_executor(None, orm_get_department_stats)

        # Створюємо Excel з кількома листами
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"statistics_{timestamp}.xlsx"
        filepath = os.path.join(ARCHIVES_PATH, filename)
        os.makedirs(ARCHIVES_PATH, exist_ok=True)

        with pd.ExcelWriter(filepath, engine="openpyxl") as writer:
            # Лист 1: Загальна статистика
            general_df = pd.DataFrame([general_stats])
            general_df = general_df.rename(
                columns={
                    "products_count": "Кількість товарів",
                    "total_value": "Загальна вартість",
                    "users_count": "Кількість користувачів",
                    "saved_lists_count": "Збережених списків",
                    "temp_items_count": "Поточних позицій",
                }
            )
            general_df.to_excel(writer, sheet_name="Загальна статистика", index=False)

            # Лист 2: По відділам
            if department_stats:
                dept_df = pd.DataFrame(department_stats)
                dept_df = dept_df.rename(
                    columns={
                        "department": "Відділ",
                        "product_count": "Кількість товарів",
                        "total_value": "Загальна вартість",
                    }
                )
                dept_df.to_excel(writer, sheet_name="По відділам", index=False)

        # Відправляємо файл
        await message.answer_document(
            FSInputFile(filepath),
            caption=f"📊 **Статистика системи**\n📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}",
        )

        # Видаляємо файл
        os.remove(filepath)

        logger.info("Експортовано статистику")

    except Exception as e:
        logger.error("Помилка експорту статистики: %s", e, exc_info=True)
        await message.answer(f"❌ Помилка експорту:\n{str(e)}")
