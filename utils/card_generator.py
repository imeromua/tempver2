# epicservice/utils/card_generator.py

import logging
from typing import Union

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message

from database.models import Product
from database.orm import (orm_get_temp_list_item_quantity,
                          orm_get_total_temp_reservation_for_product)
from keyboards.inline import get_product_actions_kb
from lexicon.lexicon import LEXICON
from utils.markdown_corrector import escape_markdown

logger = logging.getLogger(__name__)

def format_quantity(quantity_str: str) -> Union[int, float]:
    """Конвертує рядок кількості в int або float."""
    try:
        val = float(str(quantity_str).replace(',', '.'))
        return int(val) if val.is_integer() else val
    except (ValueError, TypeError):
        return 0

def get_category_emoji(department: int, group: str, name: str) -> str:
    """Підбирає емодзі залежно від категорії товару."""
    name_lower = name.lower()
    dept = int(department)

    # 610 - Фреш / Продукти
    if dept == 610:
        if any(x in name_lower for x in ['ковбас', 'м\'яс', 'сосис']): return '🥩'
        if 'сир' in name_lower: return '🧀'
        if any(x in name_lower for x in ['вино', 'горілка', 'коньяк', 'пиво']): return '🍷'
        if 'хліб' in name_lower or 'багет' in name_lower: return '🍞'
        if 'риба' in name_lower: return '🐟'
        if 'овоч' in name_lower or 'фрукт' in name_lower: return '🍎'
        return '🍽'
    
    # 70 - Електроніка / Побутова техніка
    elif dept == 70:
        if 'пилосос' in name_lower: return '🧹'
        if any(x in name_lower for x in ['бойлер', 'водонагрівач']): return '🔥'
        if 'телевізор' in name_lower: return '📺'
        if any(x in name_lower for x in ['чайник', 'кавоварка']): return '☕'
        if 'холодильник' in name_lower: return '❄️'
        return '⚡'

    # 20 - Автотовари
    elif dept == 20:
        if 'олива' in name_lower or 'масло' in name_lower: return '🛢'
        return '🚗'

    # 50 - Господарство / Сантехніка
    elif dept == 50:
        if 'змішувач' in name_lower: return '🚰'
        return '🏠'
    
    # 100 - Декор
    elif dept == 100:
        return '🎨'

    return '📦'

def format_months_no_sale(months: int) -> str:
    """Форматує рядок 'Без руху'."""
    if months is None: months = 0
    
    if months == 0:
        return "🟢 Без руху: немає даних"
    elif months <= 3:
        return f"⏱ Без руху: {months} міс"
    elif months <= 6:
        return f"⚠️ Без руху: {months} міс"
    else:
        return f"🔴 Без руху: {months} міс ⚠️"

async def send_or_edit_product_card(
    bot: Bot,
    chat_id: int,
    user_id: int,
    product: Product,
    message_id: int = None,
    search_query: str | None = None
) -> Message | None:
    """
    Формує та надсилає красиву картку товару.
    """
    try:
        # Отримуємо дані з БД
        in_user_list_qty = await orm_get_temp_list_item_quantity(user_id, product.id)
        total_reserved = await orm_get_total_temp_reservation_for_product(product.id)

        # Обробка чисел
        stock_qty = format_quantity(product.кількість)
        perm_reserved = product.відкладено or 0
        
        # Доступно = Загалом - (Постійний резерв + Тимчасові резерви інших)
        # Але ми показуємо юзеру: Залишок заг., Резерв (всіх), Доступно
        
        # Логіка відображення доступності
        available_qty = max(0, stock_qty - perm_reserved - total_reserved)
        
        # Визначення одиниці виміру (евристика: якщо float - то кг/м, інакше шт)
        is_float = isinstance(stock_qty, float)
        unit = "кг" if is_float else "шт"
        
        # Ціни та суми
        price = product.ціна or 0.0
        stock_sum_val = stock_qty * price
        
        stock_sum_str = f"{stock_sum_val:,.2f}".replace(",", " ")
        price_str = f"{price:,.2f}".replace(",", " ")

        # Емодзі категорії
        emoji = get_category_emoji(product.відділ, product.група, product.назва)
        
        # Рядок "Без руху"
        months_str = format_months_no_sale(product.місяці_без_руху)

        # Форматуємо рядки для картки
        # Залишок: 0 шт | ❌ Доступно: 0 шт
        # або
        # Залишок: 5 шт
        # 🔒 Резерв: 2 шт | ✅ Доступно: 3 шт
        
        stock_line = f"📦 Залишок: *{stock_qty}* {unit}"
        if is_float:
             stock_line = f"⚖️ Залишок: *{stock_qty}* {unit}"

        if stock_qty == 0:
            reserve_line = f"❌ Доступно: 0 {unit}"
        else:
            total_res_display = perm_reserved + total_reserved
            reserve_line = f"🔒 Резерв: {total_res_display} {unit} | ✅ Доступно: *{available_qty}* {unit}"

        # Заповнюємо шаблон
        card_text = LEXICON.PRODUCT_CARD_TEMPLATE.format(
            emoji_category=emoji,
            name=escape_markdown(product.назва),
            article=product.артикул,
            department=product.відділ,
            group=escape_markdown(product.група),
            stock_line=stock_line,
            reserve_line=reserve_line,
            price=price_str,
            unit=unit,
            stock_sum=stock_sum_str,
            months_line=months_str,
            user_qty=format_quantity(in_user_list_qty)
        )
        
        # Кнопки
        # Для кнопки "Додати все" передаємо int, якщо це можливо, або float
        qty_for_button = int(available_qty) if available_qty == int(available_qty) else available_qty
        keyboard = get_product_actions_kb(product.id, qty_for_button, search_query)

        if message_id:
            try:
                return await bot.edit_message_text(
                    text=card_text,
                    chat_id=chat_id,
                    message_id=message_id,
                    reply_markup=keyboard
                )
            except TelegramBadRequest as e:
                if "message is not modified" not in str(e):
                    logger.warning(f"Failed to edit card: {e}")
                return None
        else:
            return await bot.send_message(chat_id, card_text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"Error sending card: {e}", exc_info=True)
        await bot.send_message(chat_id, LEXICON.UNEXPECTED_ERROR)
        return None