# epicservice/utils/list_processor.py

import logging
import os
from datetime import datetime
from typing import List, Optional, Tuple

import pandas as pd
from sqlalchemy import select, delete
from sqlalchemy.orm import joinedload

from config import ARCHIVES_PATH
from database.engine import async_session
from database.models import Product, SavedList, SavedListItem, TempList, StockHistory
from database.orm import orm_clear_temp_list, orm_get_temp_list

logger = logging.getLogger(__name__)


# ==============================================================================
# 📊 ФОРМАТУВАННЯ СПИСКУ ДЛЯ ВІДОБРАЖЕННЯ
# ==============================================================================


def format_list_for_display(temp_list: List[TempList]) -> str:
    """
    Форматує тимчасовий список для відображення користувачу.
    """
    if not temp_list:
        return "📭 Ваш список порожній."

    lines = ["📦 Ваш поточний список:\n"]

    for idx, item in enumerate(temp_list, start=1):
        product = item.product
        article = product.артикул
        name = product.назва
        quantity = item.quantity

        lines.append(f"{idx}. `{article}` {name}")
        lines.append(f"   Кількість: {quantity} шт.\n")

    total_items = len(temp_list)
    total_quantity = sum(item.quantity for item in temp_list)

    lines.append(f"\n📊 Всього позицій: {total_items}")
    lines.append(f"📊 Загальна кількість: {total_quantity} шт.")

    return "\n".join(lines)


# ==============================================================================
# 💾 ЗБЕРЕЖЕННЯ СПИСКУ (СПИСАННЯ ТОВАРУ)
# ==============================================================================


async def process_and_save_list(user_id: int) -> Tuple[Optional[str], Optional[str]]:
    """
    Обробляє список:
    1. Віднімає кількість товару зі складу (Списання).
    2. Записує зміну в історію.
    3. Зберігає файли Excel.
    4. Очищає кошик.
    """
    main_list_path = None
    surplus_list_path = None

    try:
        async with async_session() as session:
            # 1. Отримуємо список
            result = await session.execute(
                select(TempList)
                .options(joinedload(TempList.product))
                .where(TempList.user_id == user_id)
            )
            temp_list = result.scalars().all()

            if not temp_list:
                logger.warning("Спроба зберегти порожній список для user_id %s", user_id)
                return None, None

            available_items_data = []
            deficit_items_data = []

            # 2. Обробка кожного товару
            for item in temp_list:
                product = item.product
                requested_qty = item.quantity

                # Парсимо поточний залишок
                try:
                    stock_qty = float(str(product.кількість).replace(",", "."))
                except (ValueError, AttributeError):
                    stock_qty = 0.0

                # Враховуємо "залізний" резерв (якщо він використовується для інших цілей),
                # але ігноруємо тимчасовий резерв цього користувача (бо ми його зараз реалізуємо).
                permanent_reserved = product.відкладено or 0
                
                # Реально доступно на складі
                real_available_stock = max(0, stock_qty - permanent_reserved)

                qty_to_deduct = 0

                if real_available_stock >= requested_qty:
                    # Достатньо товару
                    qty_to_deduct = requested_qty
                    available_items_data.append({
                        "артикул": product.артикул,
                        "назва": product.назва,
                        "кількість": requested_qty
                    })
                else:
                    # Дефіцит
                    if real_available_stock > 0:
                        # Забираємо все, що є
                        qty_to_deduct = int(real_available_stock)
                        available_items_data.append({
                            "артикул": product.артикул,
                            "назва": product.назва,
                            "кількість": qty_to_deduct
                        })
                    
                    # Решту в дефіцит
                    deficit_qty = requested_qty - real_available_stock
                    deficit_items_data.append({
                        "артикул": product.артикул,
                        "назва": product.назва,
                        "потрібно": requested_qty,
                        "є_в_наявності": real_available_stock,
                        "дефіцит": deficit_qty
                    })

                # 🔥 ГОЛОВНЕ: СПИСАННЯ ЗІ СКЛАДУ
                if qty_to_deduct > 0:
                    old_qty_str = product.кількість
                    
                    # Нова кількість
                    new_stock = stock_qty - qty_to_deduct
                    
                    # Форматування (int якщо ціле, інакше float з комою)
                    if new_stock.is_integer():
                        new_stock_str = str(int(new_stock))
                    else:
                        new_stock_str = str(new_stock).replace('.', ',')

                    # 1. Запис в історію
                    history = StockHistory(
                        product_id=product.id,
                        articul=product.артикул,
                        old_quantity=old_qty_str,
                        new_quantity=new_stock_str,
                        change_source="order" # Позначка, що це замовлення
                    )
                    session.add(history)

                    # 2. Оновлення товару
                    product.кількість = new_stock_str
                    session.add(product)

            # 3. Створення запису в історії файлів (SavedList)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            f_main = f"order_{user_id}_{timestamp}.xlsx" if available_items_data else None
            f_def = f"deficit_{user_id}_{timestamp}.xlsx" if deficit_items_data else None
            
            p_main = os.path.join(ARCHIVES_PATH, f_main) if f_main else None
            p_def = os.path.join(ARCHIVES_PATH, f_def) if f_def else None

            saved_list = SavedList(
                user_id=user_id,
                file_name=f_main or f_def,
                file_path=p_main or p_def
            )
            session.add(saved_list)
            await session.flush()

            for row in available_items_data:
                session.add(SavedListItem(
                    list_id=saved_list.id,
                    article_name=f"{row['артикул']} - {row['назва']}",
                    quantity=row['кількість']
                ))

            # 4. Очищення кошика
            await session.execute(delete(TempList).where(TempList.user_id == user_id))

            # 5. Фіксація
            await session.commit()

            # --- ГЕНЕРАЦІЯ ФАЙЛІВ ---
            os.makedirs(ARCHIVES_PATH, exist_ok=True)

            if available_items_data:
                df_main = pd.DataFrame(available_items_data)
                # Фільтруємо колонки для клієнта
                df_main[["артикул", "кількість"]].to_excel(p_main, index=False, engine="openpyxl")
                main_list_path = p_main

            if deficit_items_data:
                df_def = pd.DataFrame(deficit_items_data)
                df_def.to_excel(p_def, index=False, engine="openpyxl")
                surplus_list_path = p_def

            return main_list_path, surplus_list_path

    except Exception as e:
        logger.error("Помилка обробки списку: %s", e, exc_info=True)
        return None, None


# ==============================================================================
# 📄 ГЕНЕРАЦІЯ КАРТКИ ТОВАРУ (Запасна)
# ==============================================================================


def generate_product_card(product: Product, available_qty: float) -> str:
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
    
    return "\n".join(lines)