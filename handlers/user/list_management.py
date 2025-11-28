# epicservice/handlers/user/list_management.py

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from config import ADMIN_IDS
from database.orm import orm_clear_temp_list, orm_get_temp_list
from keyboards.reply import get_main_menu_kb, get_my_list_submenu_kb
from utils.list_processor import format_list_for_display

logger = logging.getLogger(__name__)
router = Router()


# ==============================================================================
# 📦 МІЙ СПИСОК - ПЕРЕГЛЯД
# ==============================================================================


@router.message(F.text == "📦 Переглянути список")
async def view_current_list(message: Message):
    """Показує поточний список користувача."""
    user_id = message.from_user.id
    temp_list = await orm_get_temp_list(user_id)

    if not temp_list:
        await message.answer(
            "📭 Ваш список наразі порожній.\n\n"
            "Для додавання товарів - надішліть назву або артикул.",
            reply_markup=get_my_list_submenu_kb(),
        )
        return

    # Форматуємо список
    formatted_text = format_list_for_display(temp_list)

    await message.answer(formatted_text, reply_markup=get_my_list_submenu_kb())


# ==============================================================================
# 🆕 НОВИЙ СПИСОК
# ==============================================================================


@router.message(F.text == "🆕 Створити новий")
async def create_new_list_handler(message: Message, state: FSMContext):
    """Очищає поточний список та створює новий."""
    user_id = message.from_user.id

    # Перевіряємо чи є список
    temp_list = await orm_get_temp_list(user_id)

    if not temp_list:
        await message.answer("✅ Список вже порожній. Можете починати додавати товари!")
        return

    # Очищаємо
    await orm_clear_temp_list(user_id)
    await state.clear()

    is_admin = user_id in ADMIN_IDS

    await message.answer(
        "🗑 **Поточний список видалено.**\n\n"
        "Можете починати новий збір!\n"
        "Надішліть назву або артикул товару для пошуку.",
        reply_markup=get_main_menu_kb(is_admin),
    )

    logger.info("Користувач %s створив новий список", user_id)


# ==============================================================================
# 📊 СТАТИСТИКА СПИСКУ
# ==============================================================================


@router.message(F.text == "📊 Статистика списку")
async def show_list_stats(message: Message):
    """Показує детальну статистику поточного списку."""
    user_id = message.from_user.id
    temp_list = await orm_get_temp_list(user_id)

    if not temp_list:
        await message.answer("📭 Ваш список порожній.")
        return

    # Збираємо статистику
    dept = temp_list[0].product.відділ
    total_items = len(temp_list)
    total_quantity = sum(item.quantity for item in temp_list)

    # Групуємо по групах
    groups = {}
    for item in temp_list:
        group = item.product.група
        if group not in groups:
            groups[group] = {"count": 0, "quantity": 0}
        groups[group]["count"] += 1
        groups[group]["quantity"] += item.quantity

    # Форматуємо
    text_lines = [
        f"📊 **Статистика списку**\n",
        f"**Відділ:** {dept}",
        f"**Всього позицій:** {total_items}",
        f"**Загальна кількість:** {total_quantity} шт.\n",
    ]

    if len(groups) > 0:
        text_lines.append("**По групах:**")
        for group_name, stats in sorted(groups.items()):
            text_lines.append(
                f"• {group_name}: {stats['count']} поз. ({stats['quantity']} шт.)"
            )

    await message.answer("\n".join(text_lines))
