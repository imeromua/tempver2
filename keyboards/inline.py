# epicservice/keyboards/inline.py

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from database.models import Product

def get_product_inline_kb(product_id: int, current_qty: int = 1) -> InlineKeyboardMarkup:
    """
    Картка товару:
    [➖] [✅ N шт] [➕]
    [📥 Додати все] [📝 Інша кількість]
    """
    builder = InlineKeyboardBuilder()

    # Візуалізація центральної кнопки
    if current_qty > 0:
        center_text = f"✅ {current_qty} шт"
    else:
        center_text = f"{current_qty} шт"

    builder.row(
        InlineKeyboardButton(
            text="➖", 
            callback_data=f"cart:dec:{product_id}:{current_qty}"
        ),
        InlineKeyboardButton(
            text=center_text, 
            callback_data=f"cart:add:{product_id}:{current_qty}"
        ),
        InlineKeyboardButton(
            text="➕", 
            callback_data=f"cart:inc:{product_id}:{current_qty}"
        ),
    )

    builder.row(
        InlineKeyboardButton(
            text="📥 Додати все", 
            callback_data=f"cart:all:{product_id}"
        ),
        InlineKeyboardButton(
            text="📝 Інша кількість", 
            callback_data=f"cart:manual:{product_id}"
        ),
    )

    return builder.as_markup()

def get_search_results_kb(products: list[Product]) -> InlineKeyboardMarkup:
    """
    Генерує список кнопок для результатів пошуку.
    Кожна кнопка: "Артикул | Назва" -> callback: search:prod:ID
    """
    builder = InlineKeyboardBuilder()

    for product in products:
        # Обрізаємо назву, якщо дуже довга
        name = product.назва[:30] + "..." if len(product.назва) > 30 else product.назва
        text = f"{product.артикул} | {name}"
        
        builder.row(
            InlineKeyboardButton(
                text=text,
                callback_data=f"search:prod:{product.id}"
            )
        )
    
    # Можна додати кнопку "Скасувати пошук", якщо треба
    # builder.row(InlineKeyboardButton(text="❌ Скасувати", callback_data="search:cancel"))

    return builder.as_markup()

def get_yes_no_kb(action: str) -> InlineKeyboardMarkup:
    """
    Універсальна клавіатура підтвердження.
    action: унікальний ідентифікатор дії (наприклад, 'import', 'clean_db')
    """
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Так, підтверджую", callback_data=f"confirm:{action}:yes"),
        InlineKeyboardButton(text="❌ Ні, скасувати", callback_data=f"confirm:{action}:no")
    )
    return builder.as_markup()