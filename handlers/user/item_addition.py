# epicservice/handlers/user/item_addition.py

import logging

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from database.engine import async_session
from database.orm import (
    orm_add_item_to_temp_list,
    orm_get_product_by_id,
    orm_get_temp_list_department,
    orm_get_total_temp_reservation_for_product,
)
from keyboards.reply import (
    BTN_QTY_ADD_ALL,
    BTN_QTY_CANCEL,
    BTN_QTY_CONFIRM,
    BTN_QTY_MANUAL,
    BTN_QTY_MINUS_1,
    BTN_QTY_MINUS_5,
    BTN_QTY_MINUS_10,
    BTN_QTY_PLUS_1,
    BTN_QTY_PLUS_5,
    BTN_QTY_PLUS_10,
    get_main_menu_kb,
    get_quantity_selection_kb,
)
from lexicon.lexicon import LEXICON

logger = logging.getLogger(__name__)
router = Router()


class ItemAdditionStates(StatesGroup):
    selecting_quantity = State()
    waiting_for_manual_quantity = State()


# ==============================================================================
# 🔧 БІЗНЕС-ЛОГІКА (СЕРВІСНИЙ СЛОЙ)
# ==============================================================================


async def _add_item_to_cart_service(
    user_id: int, product_id: int, quantity: int
) -> tuple[bool, str]:
    """
    Службова функція: перевіряє умови та додає товар у БД.
    Повертає кортеж: (успіх: bool, повідомлення: str).
    """
    try:
        async with async_session() as session:
            product = await orm_get_product_by_id(session, product_id)
            if not product:
                return False, LEXICON.PRODUCT_NOT_FOUND

            allowed_department = await orm_get_temp_list_department(user_id)
            if allowed_department is not None and product.відділ != allowed_department:
                return False, LEXICON.DEPARTMENT_MISMATCH.format(
                    department=allowed_department
                )

            # Перевірка кількості
            try:
                stock_quantity = float(str(product.кількість).replace(",", "."))
            except (ValueError, AttributeError):
                return False, "❌ Помилка формату кількості товару в БД."

            total_temp_reserved = await orm_get_total_temp_reservation_for_product(
                product.id
            )
            permanently_reserved = product.відкладено or 0
            available = int(stock_quantity - permanently_reserved - total_temp_reserved)

            if quantity > available:
                return (
                    False,
                    f"❌ Недостатньо товару. Доступно: {available} шт.",
                )

            await orm_add_item_to_temp_list(user_id, product_id, quantity)
            logger.info(
                "Користувач %s додав товар ID %s (кількість: %s) до списку.",
                user_id,
                product_id,
                quantity,
            )

            return True, f"✅ Додано {quantity} шт. до списку"

    except Exception as e:
        logger.error(
            "Помилка сервісу додавання товару для %s: %s", user_id, e, exc_info=True
        )
        return False, LEXICON.UNEXPECTED_ERROR


async def _get_available_quantity(product_id: int) -> int:
    """Повертає доступну кількість товару."""
    try:
        async with async_session() as session:
            product = await orm_get_product_by_id(session, product_id)
            if not product:
                return 0

            stock_quantity = float(str(product.кількість).replace(",", "."))
            total_temp_reserved = await orm_get_total_temp_reservation_for_product(
                product.id
            )
            permanently_reserved = product.відкладено or 0
            available = int(stock_quantity - permanently_reserved - total_temp_reserved)
            return max(0, available)
    except Exception as e:
        logger.error("Помилка отримання доступної кількості: %s", e, exc_info=True)
        return 0


# ==============================================================================
# 📋 ОБРОБНИКИ (ENTRY POINT - викликається з user_search.py)
# ==============================================================================


async def start_quantity_selection(
    message: Message, state: FSMContext, product_id: int
):
    """
    Запускає процес вибору кількості товару.
    Викликається з user_search.py після вибору товару.
    """
    await state.set_state(ItemAdditionStates.selecting_quantity)
    await state.update_data(product_id=product_id, current_quantity=1)

    async with async_session() as session:
        product = await orm_get_product_by_id(session, product_id)
        if not product:
            await message.answer("❌ Товар не знайдено.")
            await state.clear()
            return

        available = await _get_available_quantity(product_id)

        await message.answer(
            f"📦 **{product.назва}**\n"
            f"Артикул: `{product.артикул}`\n"
            f"Доступно: **{available}** шт.\n\n"
            f"Оберіть кількість:",
            reply_markup=get_quantity_selection_kb(current_qty=1),
        )


# ==============================================================================
# ➕➖ ЗМІНА КІЛЬКОСТІ
# ==============================================================================


@router.message(ItemAdditionStates.selecting_quantity, F.text == BTN_QTY_PLUS_1)
async def qty_plus_1(message: Message, state: FSMContext):
    data = await state.get_data()
    product_id = data.get("product_id")
    current = data.get("current_quantity", 1)
    available = await _get_available_quantity(product_id)

    new_qty = min(current + 1, available)
    await state.update_data(current_quantity=new_qty)
    await message.answer(
        f"📦 Кількість: **{new_qty}**", reply_markup=get_quantity_selection_kb(new_qty)
    )


@router.message(ItemAdditionStates.selecting_quantity, F.text == BTN_QTY_PLUS_5)
async def qty_plus_5(message: Message, state: FSMContext):
    data = await state.get_data()
    product_id = data.get("product_id")
    current = data.get("current_quantity", 1)
    available = await _get_available_quantity(product_id)

    new_qty = min(current + 5, available)
    await state.update_data(current_quantity=new_qty)
    await message.answer(
        f"📦 Кількість: **{new_qty}**", reply_markup=get_quantity_selection_kb(new_qty)
    )


@router.message(ItemAdditionStates.selecting_quantity, F.text == BTN_QTY_PLUS_10)
async def qty_plus_10(message: Message, state: FSMContext):
    data = await state.get_data()
    product_id = data.get("product_id")
    current = data.get("current_quantity", 1)
    available = await _get_available_quantity(product_id)

    new_qty = min(current + 10, available)
    await state.update_data(current_quantity=new_qty)
    await message.answer(
        f"📦 Кількість: **{new_qty}**", reply_markup=get_quantity_selection_kb(new_qty)
    )


@router.message(ItemAdditionStates.selecting_quantity, F.text == BTN_QTY_MINUS_1)
async def qty_minus_1(message: Message, state: FSMContext):
    data = await state.get_data()
    current = data.get("current_quantity", 1)

    new_qty = max(current - 1, 1)
    await state.update_data(current_quantity=new_qty)
    await message.answer(
        f"📦 Кількість: **{new_qty}**", reply_markup=get_quantity_selection_kb(new_qty)
    )


@router.message(ItemAdditionStates.selecting_quantity, F.text == BTN_QTY_MINUS_5)
async def qty_minus_5(message: Message, state: FSMContext):
    data = await state.get_data()
    current = data.get("current_quantity", 1)

    new_qty = max(current - 5, 1)
    await state.update_data(current_quantity=new_qty)
    await message.answer(
        f"📦 Кількість: **{new_qty}**", reply_markup=get_quantity_selection_kb(new_qty)
    )


@router.message(ItemAdditionStates.selecting_quantity, F.text == BTN_QTY_MINUS_10)
async def qty_minus_10(message: Message, state: FSMContext):
    data = await state.get_data()
    current = data.get("current_quantity", 1)

    new_qty = max(current - 10, 1)
    await state.update_data(current_quantity=new_qty)
    await message.answer(
        f"📦 Кількість: **{new_qty}**", reply_markup=get_quantity_selection_kb(new_qty)
    )


# ==============================================================================
# ✅ ПІДТВЕРДЖЕННЯ ТА СКАСУВАННЯ
# ==============================================================================


@router.message(ItemAdditionStates.selecting_quantity, F.text == BTN_QTY_ADD_ALL)
async def add_all_available(message: Message, state: FSMContext):
    """Додає всю доступну кількість."""
    data = await state.get_data()
    product_id = data.get("product_id")
    available = await _get_available_quantity(product_id)

    user_id = message.from_user.id
    success, result_text = await _add_item_to_cart_service(
        user_id, product_id, available
    )

    await state.clear()
    is_admin = user_id in [1962821395]  # TODO: замінити на ADMIN_IDS
    await message.answer(result_text, reply_markup=get_main_menu_kb(is_admin))


@router.message(ItemAdditionStates.selecting_quantity, F.text == BTN_QTY_CONFIRM)
async def confirm_quantity(message: Message, state: FSMContext):
    """Підтверджує вибрану кількість."""
    data = await state.get_data()
    product_id = data.get("product_id")
    quantity = data.get("current_quantity", 1)

    user_id = message.from_user.id
    success, result_text = await _add_item_to_cart_service(
        user_id, product_id, quantity
    )

    await state.clear()
    is_admin = user_id in [1962821395]  # TODO: замінити на ADMIN_IDS
    await message.answer(result_text, reply_markup=get_main_menu_kb(is_admin))


@router.message(ItemAdditionStates.selecting_quantity, F.text == BTN_QTY_CANCEL)
async def cancel_quantity_selection(message: Message, state: FSMContext):
    """Скасовує вибір кількості."""
    await state.clear()
    user_id = message.from_user.id
    is_admin = user_id in [1962821395]  # TODO: замінити на ADMIN_IDS
    await message.answer("❌ Скасовано.", reply_markup=get_main_menu_kb(is_admin))


# ==============================================================================
# ✏️ РУЧНЕ ВВЕДЕННЯ КІЛЬКОСТІ
# ==============================================================================


@router.message(ItemAdditionStates.selecting_quantity, F.text == BTN_QTY_MANUAL)
async def manual_input_trigger(message: Message, state: FSMContext):
    """Запитує ручне введення кількості."""
    await state.set_state(ItemAdditionStates.waiting_for_manual_quantity)
    await message.answer(
        "✏️ Введіть потрібну кількість числом:",
        reply_markup=get_quantity_selection_kb(1),
    )


@router.message(ItemAdditionStates.waiting_for_manual_quantity, F.text.isdigit())
async def process_manual_quantity(message: Message, state: FSMContext):
    """Обробляє вручну введену кількість."""
    data = await state.get_data()
    product_id = data.get("product_id")
    user_id = message.from_user.id

    try:
        quantity = int(message.text)
        if quantity <= 0:
            await message.answer("❌ Кількість повинна бути більше 0.")
            return

        success, result_text = await _add_item_to_cart_service(
            user_id, product_id, quantity
        )

        await state.clear()
        is_admin = user_id in [1962821395]  # TODO: замінити на ADMIN_IDS
        await message.answer(result_text, reply_markup=get_main_menu_kb(is_admin))

    except ValueError:
        await message.answer("❌ Невірний формат. Введіть число.")


@router.message(ItemAdditionStates.waiting_for_manual_quantity)
async def invalid_manual_input(message: Message):
    """Обробляє невірний формат введення."""
    await message.answer("❌ Будь ласка, введіть число.")


# ==============================================================================
