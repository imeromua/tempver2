# epicservice/utils/list_processor.py

import logging
import os
from datetime import datetime
from typing import Optional, Tuple

import pandas as pd
from sqlalchemy.ext.asyncio import AsyncSession

from config import ARCHIVES_PATH
from database.models import SavedList, SavedListItem, StockHistory
from database.orm import orm_clear_temp_list, orm_get_temp_list

logger = logging.getLogger(__name__)


async def process_and_save_list(
    session: AsyncSession, user_id: int
) -> Tuple[Optional[str], Optional[str]]:
    """
    Обробляє тимчасовий список користувача та генерує файли.
    
    Повертає кортеж: (шлях_основного_файлу, шлях_файлу_дефіциту)
    Якщо дефіциту немає, другий елемент буде None.
    """
    try:
        temp_list = await orm_get_temp_list(user_id)
        
        if not temp_list:
            logger.warning("Спроба зберегти порожній список для user_id %s", user_id)
            return None, None

        # Розподіляємо товари на доступні та дефіцит
        available_items = []
        deficit_items = []

        for item in temp_list:
            product = item.product
            
            # Парсимо кількість зі складу
            try:
                stock_qty = float(str(product.кількість).replace(",", "."))
            except (ValueError, TypeError):
                logger.error("Невірний формат кількості для товару ID %s", product.id)
                stock_qty = 0

            permanently_reserved = product.відкладено or 0
            available = int(stock_qty - permanently_reserved)

            if available >= item.quantity:
                # Товар повністю доступний
                available_items.append({
                    "Артикул": product.артикул,
                    "Назва": product.назва,
                    "Кількість": item.quantity,
                    "Відділ": product.відділ,
                    "Група": product.група,
                })
                
                # Оновлюємо залишки
                new_stock = stock_qty - item.quantity
                product.кількість = str(new_stock).replace(".", ",")
                
                # Записуємо в історію
                history = StockHistory(
                    product_id=product.id,
                    articul=product.артикул,
                    old_quantity=str(stock_qty).replace(".", ","),
                    new_quantity=str(new_stock).replace(".", ","),
                    change_source="user_list",
                )
                session.add(history)
                
            elif available > 0:
                # Частковий дефіцит
                available_items.append({
                    "Артикул": product.артикул,
                    "Назва": product.назва,
                    "Кількість": available,
                    "Відділ": product.відділ,
                    "Група": product.група,
                })
                
                deficit_items.append({
                    "Артикул": product.артикул,
                    "Назва": product.назва,
                    "Не вистачає": item.quantity - available,
                    "Відділ": product.відділ,
                })
                
                # Оновлюємо залишки до 0
                product.кількість = "0"
                
                history = StockHistory(
                    product_id=product.id,
                    articul=product.артикул,
                    old_quantity=str(stock_qty).replace(".", ","),
                    new_quantity="0",
                    change_source="user_list",
                )
                session.add(history)
                
            else:
                # Повний дефіцит
                deficit_items.append({
                    "Артикул": product.артикул,
                    "Назва": product.назва,
                    "Не вистачає": item.quantity,
                    "Відділ": product.відділ,
                })

        # Генеруємо файли
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        os.makedirs(ARCHIVES_PATH, exist_ok=True)

        main_file_path = None
        deficit_file_path = None

        # Основне замовлення
        if available_items:
            df_main = pd.DataFrame(available_items)
            main_filename = f"order_{user_id}_{timestamp}.xlsx"
            main_file_path = os.path.join(ARCHIVES_PATH, main_filename)
            df_main.to_excel(main_file_path, index=False, engine="openpyxl")
            
            # Зберігаємо в базу
            saved_list = SavedList(
                user_id=user_id,
                file_name=main_filename,
                file_path=main_file_path,
            )
            session.add(saved_list)
            await session.flush()  # Отримуємо ID
            
            # Додаємо позиції
            for item_data in available_items:
                list_item = SavedListItem(
                    list_id=saved_list.id,
                    article_name=f"{item_data['Артикул']} - {item_data['Назва']}",
                    quantity=item_data['Кількість'],
                )
                session.add(list_item)

            logger.info("Створено основне замовлення для user_id %s: %s", user_id, main_filename)

        # Файл дефіциту
        if deficit_items:
            df_deficit = pd.DataFrame(deficit_items)
            deficit_filename = f"deficit_{user_id}_{timestamp}.xlsx"
            deficit_file_path = os.path.join(ARCHIVES_PATH, deficit_filename)
            df_deficit.to_excel(deficit_file_path, index=False, engine="openpyxl")
            
            logger.info("Створено файл дефіциту для user_id %s: %s", user_id, deficit_filename)

        # Очищаємо тимчасовий список
        await orm_clear_temp_list(user_id)
        
        await session.commit()
        
        return main_file_path, deficit_file_path

    except Exception as e:
        await session.rollback()
        logger.error("Помилка обробки списку для user_id %s: %s", user_id, e, exc_info=True)
        return None, None


def format_list_for_display(temp_list: list, max_length: int = 4000) -> str:
    """
    Форматує список товарів для відображення користувачу.
    Обрізає, якщо текст занадто довгий.
    """
    if not temp_list:
        return "📭 Ваш список порожній."

    dept = temp_list[0].product.відділ
    lines = [f"📋 **Ваш список (Відділ: {dept}):**\n"]

    total_qty = 0
    for item in temp_list:
        total_qty += item.quantity
        lines.append(
            f"• `{item.product.артикул}` {item.product.назва} — **{item.quantity}**"
        )

    lines.append(f"\n🔹 Всього позицій: {len(temp_list)}")
    lines.append(f"🔹 Сума одиниць: {total_qty}")

    full_text = "\n".join(lines)
    
    if len(full_text) > max_length:
        full_text = full_text[:max_length - 50] + "\n... (список занадто довгий)"

    return full_text
