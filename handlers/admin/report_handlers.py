# epicservice/handlers/admin/report_handlers.py

import asyncio
import logging
import os
from datetime import datetime

import pandas as pd
from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import FSInputFile, Message

from config import ADMIN_IDS, ARCHIVES_PATH
from database.engine import sync_session
from database.models import Product
from keyboards.reply import get_admin_menu_kb

logger = logging.getLogger(__name__)
router = Router()


class AdminReportStates(StatesGroup):
    waiting_for_subtract_file = State()


# ==============================================================================
# 📊 ГЕНЕРАЦІЯ ЗВІТУ ПО ЗАЛИШКАХ (СИНХРОННА)
# ==============================================================================


def _create_stock_report_sync() -> str:
    """
    СИНХРОННА функція для генерації звіту по залишках.
    Використовується в executor.
    
    Returns:
        Шлях до створеного файлу або None
    """
    try:
        with sync_session() as session:
            # Отримуємо всі активні товари
            from sqlalchemy import select
            
            result = session.execute(
                select(Product).where(Product.активний == True).order_by(Product.відділ, Product.артикул)
            )
            products = result.scalars().all()

            if not products:
                logger.warning("Немає товарів для експорту")
                return None

            # Формуємо DataFrame
            data = []
            for product in products:
                data.append({
                    "Артикул": product.артикул,
                    "Назва": product.назва,
                    "Відділ": product.відділ,
                    "Група": product.група,
                    "Кількість": product.кількість,
                    "Відкладено": product.відкладено or 0,
                    "Ціна": product.ціна or 0.0,
                    "Сума залишку": product.сума_залишку or 0.0,
                    "Місяці без руху": product.місяці_без_руху or 0,
                })

            df = pd.DataFrame(data)

            # Створюємо файл
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"stock_report_{timestamp}.xlsx"
            filepath = os.path.join(ARCHIVES_PATH, filename)
            os.makedirs(ARCHIVES_PATH, exist_ok=True)

            df.to_excel(filepath, index=False, engine="openpyxl")

            logger.info("Створено звіт по залишках: %s (%s товарів)", filename, len(products))
            return filepath

    except Exception as e:
        logger.error("Помилка створення звіту по залишках: %s", e, exc_info=True)
        return None


# ==============================================================================
# 📉 ІМПОРТ ЗІБРАНОГО (ВІДНІМАННЯ)
# ==============================================================================


@router.message(AdminReportStates.waiting_for_subtract_file, F.document)
async def process_subtract_file(message: Message, state: FSMContext, bot: Bot):
    """
    Обробляє файл з зібраними товарами та віднімає їх від залишків.
    """
    if message.from_user.id not in ADMIN_IDS:
        return

    document = message.document

    if not document.file_name.endswith((".xlsx", ".xls")):
        await message.answer("❌ Невірний формат. Надішліть Excel файл (.xlsx)")
        return

    msg = await message.answer("⏳ Обробка файлу...")

    try:
        # Завантажуємо файл
        file = await bot.get_file(document.file_id)
        file_path = os.path.join(
            ARCHIVES_PATH, f"subtract_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        )
        os.makedirs(ARCHIVES_PATH, exist_ok=True)

        await bot.download_file(file.file_path, file_path)

        # Читаємо Excel
        loop = asyncio.get_running_loop()
        df = await loop.run_in_executor(None, pd.read_excel, file_path)

        # Перевірка колонок
        if "Артикул" not in df.columns or "Кількість" not in df.columns:
            await msg.edit_text(
                "❌ У файлі мають бути колонки: **Артикул** та **Кількість**"
            )
            if os.path.exists(file_path):
                os.remove(file_path)
            await state.clear()
            return

        # Віднімаємо від залишків
        from database.engine import async_session
        from database.models import StockHistory
        from sqlalchemy import select

        updated_count = 0
        not_found = []
        errors = []

        async with async_session() as session:
            for index, row in df.iterrows():
                try:
                    article = str(row["Артикул"]).strip()
                    quantity_to_subtract = float(str(row["Кількість"]).replace(",", "."))

                    # Шукаємо товар
                    result = await session.execute(
                        select(Product).where(Product.артикул == article)
                    )
                    product = result.scalar_one_or_none()

                    if not product:
                        not_found.append(article)
                        continue

                    # Парсимо поточну кількість
                    try:
                        current_qty = float(str(product.кількість).replace(",", "."))
                    except ValueError:
                        errors.append(f"{article}: невірний формат кількості")
                        continue

                    # Віднімаємо
                    new_qty = max(0, current_qty - quantity_to_subtract)
                    old_qty_str = product.кількість
                    product.кількість = str(new_qty).replace(".", ",")

                    # Записуємо в історію
                    history = StockHistory(
                        product_id=product.id,
                        articul=article,
                        old_quantity=old_qty_str,
                        new_quantity=product.кількість,
                        change_source="user_list",
                    )
                    session.add(history)

                    updated_count += 1

                except Exception as row_error:
                    errors.append(f"Рядок {index + 2}: {str(row_error)}")
                    logger.error("Помилка обробки рядка %s: %s", index + 2, row_error)

            await session.commit()

        # Видаляємо тимчасовий файл
        if os.path.exists(file_path):
            os.remove(file_path)

        # Результат
        result_text = (
            f"✅ **Імпорт зібраного завершено!**\n\n"
            f"🔄 Оновлено товарів: **{updated_count}**"
        )

        if not_found:
            result_text += f"\n❌ Не знайдено: **{len(not_found)}**"
            if len(not_found) <= 5:
                result_text += "\n• " + "\n• ".join(not_found[:5])

        if errors:
            result_text += f"\n⚠️ Помилок: **{len(errors)}**"

        await msg.edit_text(result_text)
        await state.clear()

        logger.info(
            "Імпорт зібраного: оновлено %s, не знайдено %s, помилок %s",
            updated_count,
            len(not_found),
            len(errors),
        )

    except Exception as e:
        logger.error("Критична помилка імпорту зібраного: %s", e, exc_info=True)
        await msg.edit_text(f"❌ Помилка обробки файлу:\n{str(e)}")
        await state.clear()

        if os.path.exists(file_path):
            os.remove(file_path)


@router.message(AdminReportStates.waiting_for_subtract_file)
async def invalid_subtract_file(message: Message):
    """Обробляє невірний тип повідомлення."""
    await message.answer(
        "❌ Будь ласка, надішліть Excel файл з колонками:\n"
        "• **Артикул**\n"
        "• **Кількість**\n\n"
        "Або скасуйте командою /reset"
    )
# ==============================================================================