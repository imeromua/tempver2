# epicservice/handlers/user/list_editing.py

import logging

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from config import ADMIN_IDS
from database.engine import async_session
from database.orm import (
    orm_delete_item_from_temp_list,
    orm_get_temp_list,
    orm_update_item_quantity,
)
from keyboards.reply import get_list_editing_kb, get_main_menu_kb

logger = logging.getLogger(__name__)
router = Router()


class ListEditingStates(StatesGroup):
    editing_list = State()
    waiting_for_item_number = State()
    waiting_for_new_quantity = State()


# ==============================================================================
# 📋 ПОКАЗ СПИСКУ В РЕЖИМІ РЕДАГУВАННЯ
# ==============================================================================


async def show_list_in_edit_mode(
    bot: Bot, chat_id: int, user_id: int, state: FSMContext
):
    """Показує список товарів з нумерацією для редагування."""
    temp_list = await orm_get_temp_list(user_id)

    if not temp_list:
        is_admin = user_id in ADMIN_IDS
        await bot.send_message(
            chat_id,
            "📭 Ваш список порожній.",
            reply_markup=get_main_menu_kb(is_admin),
        )
        await state.clear()
        return

    dept = temp_list[0].product.відділ
    text_lines = [f"✏️ **Редагування списку (Відділ: {dept})**\n"]

    for idx, item in enumerate(temp_list, start=1):
        text_lines.append(
            f"{idx}. `{item.product.артикул}` {item.product.назва}\n"
            f"   Кількість: **{item.quantity}** шт.\n"
        )

    text_lines.append(
        "\n📝 **Команди:**\n"
        "• `N` - вибрати позицію №N (наприклад: `3`)\n"
        "• `N 0` - видалити позицію №N (наприклад: `3 0`)\n"
        "• `N K` - змінити кількість позиції №N на K (наприклад: `3 15`)\n"
        "• Або використайте кнопки нижче"
    )

    full_text = "\n".join(text_lines)
    if len(full_text) > 4000:
        full_text = full_text[:3900] + "\n... (список занадто довгий)"

    await bot.send_message(chat_id, full_text, reply_markup=get_list_editing_kb())
    await state.set_state(ListEditingStates.editing_list)


# ==============================================================================
# ✅ ЗАВЕРШЕННЯ РЕДАГУВАННЯ
# ==============================================================================


@router.message(ListEditingStates.editing_list, F.text == "✅ Завершити редагування")
async def finish_editing(message: Message, state: FSMContext):
    """Завершує режим редагування."""
    await state.clear()
    user_id = message.from_user.id
    is_admin = user_id in ADMIN_IDS

    await message.answer(
        "✅ Редагування завершено.", reply_markup=get_main_menu_kb(is_admin)
    )


# ==============================================================================
# 📝 ОБРОБКА КОМАНД РЕДАГУВАННЯ
# ==============================================================================


@router.message(ListEditingStates.editing_list, F.text.regexp(r"^\d+$"))
async def select_item_by_number(message: Message, state: FSMContext, bot: Bot):
    """Обробляє вибір позиції за номером (наприклад: '3')."""
    user_id = message.from_user.id
    temp_list = await orm_get_temp_list(user_id)

    try:
        item_number = int(message.text)
        if item_number < 1 or item_number > len(temp_list):
            await message.answer(
                f"❌ Невірний номер. Оберіть від 1 до {len(temp_list)}."
            )
            return

        selected_item = temp_list[item_number - 1]
        await state.update_data(selected_item_id=selected_item.id)
        await state.set_state(ListEditingStates.waiting_for_new_quantity)

        await message.answer(
            f"📦 Обрано: **{selected_item.product.назва}**\n"
            f"Поточна кількість: **{selected_item.quantity}** шт.\n\n"
            f"Введіть нову кількість (або `0` для видалення):"
        )

    except ValueError:
        await message.answer("❌ Невірний формат. Введіть число.")


@router.message(ListEditingStates.editing_list, F.text.regexp(r"^\d+\s+\d+$"))
async def quick_edit_item(message: Message, state: FSMContext, bot: Bot):
    """Обробляє швидке редагування (наприклад: '3 15' або '3 0')."""
    user_id = message.from_user.id
    temp_list = await orm_get_temp_list(user_id)

    try:
        parts = message.text.split()
        item_number = int(parts[0])
        new_quantity = int(parts[1])

        if item_number < 1 or item_number > len(temp_list):
            await message.answer(
                f"❌ Невірний номер. Оберіть від 1 до {len(temp_list)}."
            )
            return

        selected_item = temp_list[item_number - 1]

        if new_quantity == 0:
            # Видалення
            await orm_delete_item_from_temp_list(selected_item.id)
            await message.answer(f"🗑 Позицію #{item_number} видалено.")
        elif new_quantity > 0:
            # Зміна кількості
            async with async_session() as session:
                await orm_update_item_quantity(session, selected_item.id, new_quantity)
            await message.answer(
                f"✅ Позицію #{item_number} оновлено: **{new_quantity}** шт."
            )
        else:
            await message.answer("❌ Кількість повинна бути >= 0.")
            return

        # Оновлюємо список
        await show_list_in_edit_mode(bot, message.chat.id, user_id, state)

    except (ValueError, IndexError):
        await message.answer("❌ Невірний формат. Використайте: `N K` (наприклад: `3 15`)")


# ==============================================================================
# 🔢 ОБРОБКА НОВОЇ КІЛЬКОСТІ
# ==============================================================================


@router.message(ListEditingStates.waiting_for_new_quantity, F.text.regexp(r"^\d+$"))
async def process_new_quantity(message: Message, state: FSMContext, bot: Bot):
    """Обробляє введену нову кількість."""
    user_id = message.from_user.id
    data = await state.get_data()
    item_id = data.get("selected_item_id")

    try:
        new_quantity = int(message.text)

        if new_quantity == 0:
            # Видалення
            await orm_delete_item_from_temp_list(item_id)
            await message.answer("🗑 Позицію видалено.")
        elif new_quantity > 0:
            # Оновлення кількості
            async with async_session() as session:
                await orm_update_item_quantity(session, item_id, new_quantity)
            await message.answer(f"✅ Кількість оновлено: **{new_quantity}** шт.")
        else:
            await message.answer("❌ Кількість повинна бути >= 0.")
            return

        # Повертаємось до списку
        await state.set_state(ListEditingStates.editing_list)
        await show_list_in_edit_mode(bot, message.chat.id, user_id, state)

    except ValueError:
        await message.answer("❌ Невірний формат. Введіть число.")


@router.message(ListEditingStates.waiting_for_new_quantity)
async def invalid_quantity_input(message: Message):
    """Обробляє невірний формат введення кількості."""
    await message.answer("❌ Будь ласка, введіть число (або `0` для видалення).")


# ==============================================================================
# ❌ ОБРОБКА НЕВІДОМИХ КОМАНД В РЕЖИМІ РЕДАГУВАННЯ
# ==============================================================================


@router.message(ListEditingStates.editing_list)
async def unknown_editing_command(message: Message):
    """Обробляє невідомі команди в режимі редагування."""
    await message.answer(
        "❌ Невідома команда.\n\n"
        "**Доступні формати:**\n"
        "• `N` - вибрати позицію\n"
        "• `N K` - змінити кількість\n"
        "• `N 0` - видалити позицію\n\n"
        "Або використайте кнопку '✅ Завершити редагування'"
    )
# ==============================================================================