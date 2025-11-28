# epicservice/handlers/user/item_addition.py

import logging
from contextlib import suppress

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select, func, and_

from config import ADMIN_IDS
from database.engine import async_session
from database.models import TempList
from database.orm import (
    orm_add_item_to_temp_list,
    orm_get_product_by_id,
    orm_get_temp_list_department,
)
from keyboards.inline import get_product_inline_kb
from keyboards.reply import get_main_menu_kb
from utils.card_generator import format_product_card

logger = logging.getLogger(__name__)
router = Router()

class ItemAdditionStates(StatesGroup):
    waiting_for_manual_quantity = State()

# ==============================================================================
# 🛠 ДОПОМІЖНІ ФУНКЦІЇ
# ==============================================================================

async def _get_product_data(user_id: int, product_id: int):
    """
    Збирає всі дані про товар в ОДНІЙ сесії.
    """
    async with async_session() as session:
        product = await orm_get_product_by_id(session, product_id)
        if not product:
            return None

        # Резерви (глобальні)
        res_reserved = await session.execute(
            select(func.sum(TempList.quantity)).where(TempList.product_id == product_id)
        )
        total_reserved = res_reserved.scalar_one_or_none()
        temp_reserved = int(total_reserved) if total_reserved else 0

        # У кошику користувача
        res_cart = await session.execute(
            select(TempList).where(
                and_(TempList.user_id == user_id, TempList.product_id == product_id)
            )
        )
        cart_item = res_cart.scalar_one_or_none()
        in_cart = cart_item.quantity if cart_item else 0

        # Доступність
        try:
            stock_qty = float(str(product.кількість).replace(",", "."))
        except ValueError:
            stock_qty = 0
            
        permanently_reserved = product.відкладено or 0
        available = max(0, int(stock_qty - permanently_reserved - temp_reserved))

        return product, available, temp_reserved, in_cart

async def update_card_display(
    bot: Bot, 
    chat_id: int, 
    message_id: int, 
    user_id: int, 
    product_id: int, 
    current_ui_qty: int
):
    """Оновлює картку та клавіатуру."""
    data = await _get_product_data(user_id, product_id)
    if not data:
        return

    product, available, temp_reserved, in_cart = data
    
    new_text = format_product_card(
        product, available, temp_reserved, in_cart, selected_quantity=current_ui_qty
    )
    new_kb = get_product_inline_kb(product_id, current_ui_qty)

    with suppress(TelegramBadRequest):
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=new_text,
            reply_markup=new_kb
        )

# ==============================================================================
# 🚀 ENTRY POINT
# ==============================================================================

async def start_quantity_selection(message: Message, state: FSMContext, product_id: int):
    """Початок вибору."""
    user_id = message.from_user.id
    
    data = await _get_product_data(user_id, product_id)
    if not data:
        await message.answer("❌ Товар не знайдено.")
        return

    product, available, temp_reserved, in_cart = data
    
    # СТАРТ З 0 (як просили)
    start_qty = 0
    
    text = format_product_card(
        product, available, temp_reserved, in_cart, selected_quantity=start_qty
    )
    kb = get_product_inline_kb(product_id, current_qty=start_qty)

    await message.answer(text, reply_markup=kb)

# ==============================================================================
# ⚡ ОБРОБКА КНОПОК
# ==============================================================================

@router.callback_query(F.data.startswith("cart:inc:"))
async def on_increment(callback: CallbackQuery):
    _, _, product_id, current_qty = callback.data.split(":")
    product_id = int(product_id)
    current_qty = int(current_qty)
    
    data = await _get_product_data(callback.from_user.id, product_id)
    if not data: return
    _, available, _, _ = data

    if current_qty >= available:
        await callback.answer(f"⚠️ Доступно лише {available} шт.", show_alert=True)
        return

    new_qty = current_qty + 1
    await update_card_display(
        callback.bot, callback.message.chat.id, callback.message.message_id,
        callback.from_user.id, product_id, new_qty
    )
    await callback.answer() 

@router.callback_query(F.data.startswith("cart:dec:"))
async def on_decrement(callback: CallbackQuery):
    _, _, product_id, current_qty = callback.data.split(":")
    product_id = int(product_id)
    current_qty = int(current_qty)

    # Дозволяємо зменшувати до 0
    if current_qty <= 0:
        await callback.answer("⚠️ Мінімум 0 шт.")
        return

    new_qty = current_qty - 1
    await update_card_display(
        callback.bot, callback.message.chat.id, callback.message.message_id,
        callback.from_user.id, product_id, new_qty
    )
    await callback.answer()

@router.callback_query(F.data.startswith("cart:add:"))
async def on_add(callback: CallbackQuery):
    """Додає товар (клік по центральній кнопці)."""
    _, _, product_id, qty = callback.data.split(":")
    product_id = int(product_id)
    qty = int(qty)
    user_id = callback.from_user.id

    # ЗАБОРОНА додавати 0
    if qty <= 0:
        await callback.answer("⚠️ Оберіть кількість більше 0!", show_alert=True)
        return

    # Перевірка відділу
    async with async_session() as session:
        product = await orm_get_product_by_id(session, product_id)
        allowed_dept = await orm_get_temp_list_department(user_id)
        
        if allowed_dept is not None and product.відділ != allowed_dept:
            await callback.answer(
                f"🚫 Інший відділ! Потрібен {allowed_dept}.", show_alert=True
            )
            return

    success = await orm_add_item_to_temp_list(user_id, product_id, qty)
    
    if success:
        await callback.answer(f"✅ Додано {qty} шт.", show_alert=False)
        # Скидаємо селектор на 0 після успішного додавання
        await update_card_display(
            callback.bot, callback.message.chat.id, callback.message.message_id,
            user_id, product_id, 0
        )
    else:
        await callback.answer("❌ Помилка додавання", show_alert=True)

@router.callback_query(F.data.startswith("cart:all:"))
async def on_add_all(callback: CallbackQuery):
    _, _, product_id = callback.data.split(":")
    product_id = int(product_id)
    user_id = callback.from_user.id

    data = await _get_product_data(user_id, product_id)
    if not data: return
    product, available, _, _ = data

    if available <= 0:
        await callback.answer("❌ Немає в наявності", show_alert=True)
        return

    allowed_dept = await orm_get_temp_list_department(user_id)
    if allowed_dept is not None and product.відділ != allowed_dept:
        await callback.answer(f"🚫 Інший відділ", show_alert=True)
        return

    await orm_add_item_to_temp_list(user_id, product_id, available)
    await callback.answer(f"✅ Додано все ({available} шт)", show_alert=False)
    
    # Скидаємо на 0
    await update_card_display(
        callback.bot, callback.message.chat.id, callback.message.message_id,
        user_id, product_id, 0
    )

# ==============================================================================
# 📝 РУЧНЕ ВВЕДЕННЯ
# ==============================================================================

@router.callback_query(F.data.startswith("cart:manual:"))
async def on_manual_input(callback: CallbackQuery, state: FSMContext):
    _, _, product_id = callback.data.split(":")
    await state.set_state(ItemAdditionStates.waiting_for_manual_quantity)
    await state.update_data(product_id=int(product_id))
    await callback.message.answer("✏️ Введіть кількість (числом):")
    await callback.answer()

@router.message(ItemAdditionStates.waiting_for_manual_quantity)
async def process_manual_qty(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ Введіть число.")
        return

    qty = int(message.text)
    if qty <= 0:
        await message.answer("❌ Число > 0.")
        return

    data = await state.get_data()
    product_id = data.get("product_id")
    user_id = message.from_user.id

    data_prod = await _get_product_data(user_id, product_id)
    if not data_prod: return
    product, available, _, _ = data_prod
    
    allowed_dept = await orm_get_temp_list_department(user_id)
    if allowed_dept is not None and product.відділ != allowed_dept:
        await message.answer(f"🚫 Невірний відділ.")
        await state.clear()
        return

    if qty > available:
        await message.answer(f"⚠️ Недостатньо. Є лише {available} шт.")
        return

    await orm_add_item_to_temp_list(user_id, product_id, qty)
    
    is_admin = user_id in ADMIN_IDS
    await message.answer(f"✅ Додано {qty} шт.", reply_markup=get_main_menu_kb(is_admin))
    await state.clear()