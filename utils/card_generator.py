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
) -> str:
    """
    Форматує картку товару з детальною інформацією.

    Args:
        product: Об'єкт товару з БД
        available_qty: Доступна кількість для замовлення
        temp_reserved: Кількість в тимчасових резервах

    Returns:
        Відформатований текст картки
    """
    try:
        # Парсимо кількість зі складу
        stock_qty_str = str(product.кількість).replace(",", ".")
        try:
            stock_qty = float(stock_qty_str)
        except ValueError:
            stock_qty = 0

        # Інформація про резерви
        permanently_reserved = product.відкладено or 0

        # Базова інформація
        lines = [
            f"📦 **{product.назва}**\n",
            f"**Артикул:** `{product.артикул}`",
            f"**Відділ:** {product.відділ}",
            f"**Група:** {product.група}",
            "",
            f"**На складі:** {product.кількість}",
        ]

        # Резерви
        if permanently_reserved > 0:
            lines.append(f"**Відкладено:** {permanently_reserved}")

        if temp_reserved > 0:
            lines.append(f"**В резерві (інші користувачі):** {temp_reserved}")

        # Доступна кількість
        if available_qty > 0:
            lines.append(f"\n✅ **Доступно для замовлення:** {available_qty} шт.")
        else:
            lines.append(f"\n❌ **Товар відсутній**")

        # Додаткова інформація (якщо є)
        if product.ціна and product.ціна > 0:
            lines.append(f"**Ціна:** {product.ціна:.2f} грн")

        if product.сума_залишку and product.сума_залишку > 0:
            lines.append(f"**Сума залишку:** {product.сума_залишку:.2f} грн")

        if product.місяці_без_руху and product.місяці_без_руху > 0:
            lines.append(f"⚠️ Без руху: {product.місяці_без_руху} міс.")

        return "\n".join(lines)

    except Exception as e:
        logger.error(
            "Помилка форматування картки товару ID %s: %s", product.id, e, exc_info=True
        )
        return f"📦 **{product.назва}**\nАртикул: `{product.артикул}`\n\n❌ Помилка відображення деталей"


async def send_or_edit_product_card(
    bot: Bot,
    chat_id: int,
    user_id: int,
    product: Product,
    message_id: Optional[int] = None,
) -> Optional[Message]:
    """
    Надсилає або редагує картку товару.

    Args:
        bot: Екземпляр бота
        chat_id: ID чату
        user_id: ID користувача
        product: Об'єкт товару
        message_id: ID повідомлення для редагування (якщо потрібно)

    Returns:
        Надіслане або відредаговане повідомлення
    """
    try:
        # Отримуємо інформацію про резерви
        temp_reserved = await orm_get_total_temp_reservation_for_product(product.id)

        # Рахуємо доступну кількість
        try:
            stock_qty = float(str(product.кількість).replace(",", "."))
        except ValueError:
            stock_qty = 0

        permanently_reserved = product.відкладено or 0
        available = max(0, int(stock_qty - permanently_reserved - temp_reserved))

        # Форматуємо картку
        card_text = format_product_card(product, available, temp_reserved)

        # Надсилаємо або редагуємо
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
                    logger.debug("Повідомлення не змінилось, пропускаємо редагування")
                    return None
                raise
        else:
            return await bot.send_message(chat_id, card_text)

    except Exception as e:
        logger.error(
            "Помилка відправки/редагування картки товару ID %s: %s",
            product.id,
            e,
            exc_info=True,
        )
        return None


def format_product_short(product: Product) -> str:
    """
    Короткий формат товару (для списків).

    Returns:
        Компактний рядок з основною інформацією
    """
    return f"`{product.артикул}` {product.назва} | {product.кількість} шт."


def format_search_result(product: Product, index: int, similarity: int = 0) -> str:
    """
    Форматує товар для відображення в результатах пошуку.

    Args:
        product: Товар
        index: Порядковий номер
        similarity: Відсоток схожості (0-100)

    Returns:
        Відформатований рядок
    """
    result = f"{index}. `{product.артикул}` **{product.назва}**\n"
    result += f"   Відділ: {product.відділ} | Залишок: {product.кількість}"

    if similarity > 0:
        result += f"\n   Схожість: {similarity}%"

    return result + "\n"


def validate_product_availability(
    product: Product, requested_qty: int
) -> tuple[bool, str]:
    """
    Перевіряє чи доступна потрібна кількість товару.

    Returns:
        (доступність: bool, повідомлення: str)
    """
    if not product.активний:
        return False, "❌ Товар деактивований."

    try:
        stock_qty = float(str(product.кількість).replace(",", "."))
    except ValueError:
        return False, "❌ Помилка формату кількості товару."

    if stock_qty <= 0:
        return False, "❌ Товар відсутній на складі."

    permanently_reserved = product.відкладено or 0
    available = int(stock_qty - permanently_reserved)

    if requested_qty > available:
        return False, f"❌ Недостатньо товару. Доступно: {available} шт."

    return True, "✅ Товар доступний"
