# epicservice/keyboards/inline.py

from typing import Union

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


# --- КНОПКИ ДЛЯ КАРТКИ ТОВАРУ ---
def get_product_actions_kb(
    product_id: int,
    available_quantity: Union[int, float],
    search_query: str | None = None,
) -> InlineKeyboardMarkup:
    qty_text = (
        f"{available_quantity:.2f}"
        if isinstance(available_quantity, float)
        else str(available_quantity)
    )

    actions = []
    # Кнопки дій з товаром
    if available_quantity > 0:
        actions.append(
            InlineKeyboardButton(
                text=f"✅ Додати все ({qty_text})",
                callback_data=f"add_all:{product_id}:{available_quantity}",
            )
        )

    actions.append(
        InlineKeyboardButton(
            text="📝 Ввести кількість", callback_data=f"select_quantity:{product_id}"
        )
    )

    # ВИДАЛЕНО: Кнопки навігації ("Назад до пошуку", "Мій список"), бо вони є внизу на клавіатурі.
    # Залишаємо тільки функціональні кнопки.

    return InlineKeyboardMarkup(
        inline_keyboard=[
            actions if len(actions) > 0 else [],
            # Можна додати кнопку "Приховати", щоб прибрати картку
            [
                InlineKeyboardButton(
                    text="❌ Приховати картку", callback_data="card:close"
                )
            ],
        ]
    )


# --- ІНШІ КЛАВІАТУРИ ---


def get_quantity_selector_kb(
    product_id: int, current_qty: int, max_qty: int
) -> InlineKeyboardMarkup:
    # Залишаємо як є, це функціонал
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="➖",
                    callback_data=f"qty_update:{product_id}:minus:{current_qty}:{max_qty}",
                ),
                InlineKeyboardButton(
                    text=f"✅ {current_qty} шт",
                    callback_data=f"add_confirm:{product_id}:{current_qty}",
                ),
                InlineKeyboardButton(
                    text="➕",
                    callback_data=f"qty_update:{product_id}:plus:{current_qty}:{max_qty}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="📝 Ввести число",
                    callback_data=f"qty_manual_input:{product_id}",
                )
            ],
        ]
    )


def get_confirmation_kb(
    confirm_callback: str, cancel_callback: str
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Так", callback_data=confirm_callback),
                InlineKeyboardButton(text="❌ Ні", callback_data=cancel_callback),
            ]
        ]
    )


# --- СТАРІ МЕНЮ ВИДАЛЯЄМО АБО ЗАЛИШАЄМО ПУСТИМИ ---
# (Вони більше не використовуються, навігація йде через Reply)
