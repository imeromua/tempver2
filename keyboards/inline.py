# epicservice/keyboards/inline.py

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

def get_product_inline_kb(product_id: int, current_qty: int = 1) -> InlineKeyboardMarkup:
    """
    Layout:
    [➖] [0 шт] [➕] (якщо 0)
    [➖] [✅ N шт] [➕] (якщо > 0)
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