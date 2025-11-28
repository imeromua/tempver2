# epicservice/utils/list_processor.py

import logging
import os
from datetime import datetime
from typing import List, Optional, Tuple

import pandas as pd

from config import ARCHIVES_PATH
from database.engine import async_session
from database.models import Product, SavedList, SavedListItem, TempList
from database.orm import orm_clear_temp_list, orm_get_temp_list

logger = logging.getLogger(__name__)


# ==============================================================================
# 📊 ФОРМАТУВАННЯ СПИСКУ ДЛЯ ВІДОБРАЖЕННЯ
# ==============================================================================


def format_list_for_display(temp_list: List[TempList]) -> str:
    """
    Форматує тимчасовий список для відображення користувачу.
    
    Args:
        temp_list: Список позицій TempList
    
    Returns:
        Відформатований текст для відправки користувачу
    """
    if not temp_list:
        return "📭 Ваш список порожній."

    lines = ["📦 Ваш поточний список:\n"]

    for idx, item in enumerate(temp_list, start=1):
        product = item.product
        article = product.артикул
        name = product.назва
        quantity = item.quantity

        lines.append(f"{idx}. {article} - {name}")
        lines.append(f"   Кількість: {quantity} шт.\n")

    total_items = len(temp_list)
    total_quantity = sum(item.quantity for item in temp_list)

    lines.append(f"\n📊 Всього позицій: {total_items}")
    lines.append(f"📊 Загальна кількість: {total_quantity} шт.")

    return "\n".join(lines)


# ==============================================================================
# 💾 ЗБЕРЕЖЕННЯ СПИСКУ
# ==============================================================================


async def process_and_save_list(user_id: int) -> Tuple[Optional[str], Optional[str]]:
    """
    Обробляє тимчасовий список користувача та зберігає його.
    
    Розділяє товари на:
    - Доступні (основне замовлення)
    - Дефіцит (недостатньо на складі)
    
    Args:
        user_id: ID користувача
    
    Returns:
        Tuple[main_list_path, surplus_list_path] - шляхи до створених файлів
        (None, None) якщо список порожній або помилка
    """
    try:
        # Отримуємо тимчасовий список
        temp_list = await orm_get_temp_list(user_id)

        if not temp_list:
            logger.warning("Спроба зберегти порожній список для user_id %s", user_id)
            return None, None

        # Розділяємо на доступні та дефіцит
        available_items = []
        deficit_items = []

        for item in temp_list:
            product = item.product
            requested_qty = item.quantity

            # Парсимо кількість на складі
            try:
                stock_qty = float(str(product.кількість).replace(",", "."))
            except (ValueError, AttributeError):
                stock_qty = 0.0

            # Резерв (відкладено)
            reserved_qty = product.відкладено or 0

            # Доступна кількість = залишок - відкладено
            available_qty = max(0, stock_qty - reserved_qty)

            if available_qty >= requested_qty:
                # Достатньо на складі
                available_items.append({
                    "артикул": product.артикул,
                    "назва": product.назва,
                    "група": product.група,
                    "кількість": requested_qty,
                    "залишок": stock_qty,
                })
            else:
                # Недостатньо
                if available_qty > 0:
                    # Частково є
                    available_items.append({
                        "артикул": product.артикул,
                        "назва": product.назва,
                        "група": product.група,
                        "кількість": available_qty,
                        "залишок": stock_qty,
                    })

                # Дефіцит
                deficit_qty = requested_qty - available_qty
                deficit_items.append({
                    "артикул": product.артикул,
                    "назва": product.назва,
                    "група": product.група,
                    "потрібно": requested_qty,
                    "є_в_наявності": available_qty,
                    "дефіцит": deficit_qty,
                })

        # Створюємо файли
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        os.makedirs(ARCHIVES_PATH, exist_ok=True)

        main_list_path = None
        surplus_list_path = None

        # Основне замовлення
        if available_items:
            main_filename = f"order_{user_id}_{timestamp}.xlsx"
            main_list_path = os.path.join(ARCHIVES_PATH, main_filename)

            df_main = pd.DataFrame(available_items)
            df_main.to_excel(main_list_path, index=False, engine="openpyxl")

            logger.info("Створено основне замовлення для user_id %s: %s", user_id, main_filename)

        # Дефіцит
        if deficit_items:
            deficit_filename = f"deficit_{user_id}_{timestamp}.xlsx"
            surplus_list_path = os.path.join(ARCHIVES_PATH, deficit_filename)

            df_deficit = pd.DataFrame(deficit_items)
            df_deficit.to_excel(surplus_list_path, index=False, engine="openpyxl")

            logger.info("Створено список дефіциту для user_id %s: %s", user_id, deficit_filename)

        # Зберігаємо в БД
        async with async_session() as session:
            # Створюємо запис SavedList
            saved_list = SavedList(
                user_id=user_id,
                file_name=main_filename if main_list_path else deficit_filename,
                file_path=main_list_path if main_list_path else surplus_list_path,
            )
            session.add(saved_list)
            await session.flush()  # Отримуємо ID

            # Зберігаємо позиції
            for item_data in available_items:
                saved_item = SavedListItem(
                    list_id=saved_list.id,
                    article_name=f"{item_data['артикул']} - {item_data['назва']}",
                    quantity=item_data['кількість'],
                )
                session.add(saved_item)

            await session.commit()

        # ВАЖЛИВО: Очищаємо тимчасовий список ПІСЛЯ збереження
        await orm_clear_temp_list(user_id)

        return main_list_path, surplus_list_path

    except Exception as e:
        logger.error("Помилка обробки списку для user_id %s: %s", user_id, e, exc_info=True)
        return None, None


# ==============================================================================
# 📄 ГЕНЕРАЦІЯ КАРТКИ ТОВАРУ
# ==============================================================================


def generate_product_card(product: Product, available_qty: float) -> str:
    """
    Генерує текстову картку товару для відображення.
    
    Args:
        product: Об'єкт Product
        available_qty: Доступна кількість
    
    Returns:
        Відформатований текст картки
    """
    lines = [
        f"🏷 Артикул: {product.артикул}",
        f"📦 Назва: {product.назва}",
        f"🏢 Відділ: {product.відділ}",
        f"📂 Група: {product.група}",
        f"",
        f"📊 Залишок: {product.кількість} шт.",
    ]

    if product.відкладено:
        lines.append(f"🔒 Відкладено: {product.відкладено} шт.")

    lines.append(f"✅ Доступно: {available_qty} шт.")

    if product.ціна:
        lines.append(f"💰 Ціна: {product.ціна:.2f} грн")

    if product.місяці_без_руху and product.місяці_без_руху > 0:
        lines.append(f"⏱ Без руху: {product.місяці_без_руху} міс.")

    return "\n".join(lines)
