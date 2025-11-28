# epicservice/utils/card_generator.py

import logging
from typing import Optional

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message

from database.models import Product
from database.orm import orm_get_total_temp_reservation_for_product

logger = logging.getLogger(__name__)


def format_product_card(
    product: Product,
    available_qty: int,
    temp_reserved: int = 0,
    in_cart_qty: int = 0,
    selected_quantity: Optional[int] = None,
) -> str:
    """
    Форматує картку товару.
    """
    try:
        try:
            stock_qty = float(str(product.кількість).replace(",", "."))
        except ValueError:
            stock_qty = 0

        price = product.ціна or 0.0
        
        # Базові резерви
        permanently_reserved = product.відкладено or 0
        total_db_reserved = permanently_reserved + temp_reserved
        
        # --- ДИНАМІЧНИЙ РОЗРАХУНОК ---
        if selected_quantity is not None:
            if selected_quantity == 0:
                # СПЕЦІАЛЬНИЙ ВИПАДОК ДЛЯ 0:
                # Показуємо ціну за 1 шт як довідкову
                current_sum = price
                sum_label = "Сума (1 шт)"
                
                # Резерви і доступність НЕ змінюємо (бо 0 обрано)
                display_available = available_qty
                display_reserved = total_db_reserved
            else:
                # Стандартний розрахунок для > 0
                current_sum = price * selected_quantity
                sum_label = f"Сума ({selected_quantity} шт)"
                
                display_available = max(0, available_qty - selected_quantity)
                display_reserved = total_db_reserved + selected_quantity
        else:
            # Режим перегляду (без селектора)
            current_sum = price * available_qty
            sum_label = f"Сума ({available_qty} шт)"
            display_available = available_qty
            display_reserved = total_db_reserved
        
        months = product.місяці_без_руху or 0

        # --- ФОРМУВАННЯ ТЕКСТУ ---
        lines = [
            f"📦 **{product.назва}**",
            f"🔢 Артикул: `{product.артикул}`",
            f"🏢 Відділ: {product.відділ} | 📂 Група: {product.група}",
            "━━━━━━━━━━━━━━━━━━━━",
            "📊 **ЗАЛИШКИ:**",
            f"📦 Залишок: {stock_qty:g} шт",
        ]

        lines.append(f"🔒 Резерв: {display_reserved} шт | ✅ Доступно: {display_available} шт")

        lines.append("━━━━━━━━━━━━━━━━━━━━")
        lines.append("💰 **ВАРТІСТЬ:**")
        
        lines.append(
            f"💵 Ціна: {price:,.2f} грн/шт | 💸 {sum_label}: {current_sum:,.2f} грн".replace(",", " ")
        )
        
        if months > 0:
            lines.append(f"⏱ Без руху: {months} міс")

        lines.append("━━━━━━━━━━━━━━━━━━━━")
        
        return "\n".join(lines)

    except Exception as e:
        logger.error(
            "Помилка форматування картки товару ID %s: %s", product.id, e, exc_info=True
        )
        return f"📦 **{product.назва}**\n❌ Помилка відображення деталей"


async def send_or_edit_product_card(
    bot: Bot,
    chat_id: int,
    user_id: int,
    product: Product,
    message_id: Optional[int] = None,
    in_cart_qty: int = 0,
    selected_qty: Optional[int] = None,
) -> Optional[Message]:
    """
    Універсальна функція для відправки або редагування картки товару.
    """
    try:
        # Отримуємо інформацію про резерви
        temp_reserved = await orm_get_total_temp_reservation_for_product(product.id)

        try:
            stock_qty = float(str(product.кількість).replace(",", "."))
        except ValueError:
            stock_qty = 0

        permanently_reserved = product.відкладено or 0
        available = max(0, int(stock_qty - permanently_reserved - temp_reserved))

        card_text = format_product_card(
            product, available, temp_reserved, in_cart_qty, selected_qty
        )

        if message_id:
            try:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=card_text,
                )
                return None
            except TelegramBadRequest as e:
                if "message is not modified" in str(e).lower():
                    return None
                raise
        else:
            return await bot.send_message(chat_id, card_text)

    except Exception as e:
        logger.error(
            "Помилка відправки картки ID %s: %s",
            product.id,
            e,
            exc_info=True,
        )
        return None