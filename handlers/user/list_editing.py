# epicservice/handlers/user/list_editing.py

import logging

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from database.engine import async_session
from database.orm import (
    orm_delete_temp_list_item,
    orm_get_product_by_id,
    orm_get_temp_list,
    orm_update_temp_list_item_quantity,
)
from keyboards.reply import get_my_list_submenu_kb

logger = logging.getLogger(__name__)
router = Router()


class ListEditingStates(StatesGroup):
    editing_list = State()
    waiting_for_new_quantity = State()


# --- ДОПОМІЖНА ФУНКЦІЯ: ГЕНЕРАЦІЯ ІНЛАЙН СПИСКУ ---
def get_editing_kb(temp_list) -> InlineKeyboardMarkup:
    kb = []
    for item in temp_list:
        # Кнопка: "Артикул | Назва (К-сть)" -> callback="edit_item:ID"
        btn_text = f"✏️ {item.quantity} шт. | {item.product.назва[:20]}"
        kb.append(
            [
                InlineKeyboardButton(
                    text=btn_text, callback_data=f"edit_item:{item.product.id}"
                )
            ]
        )

    # Кнопка завершення
    kb.append(
        [
            InlineKeyboardButton(
                text="✅ Завершити редагування", callback_data="edit_list:finish"
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=kb)


# --- ВІДОБРАЖЕННЯ ЕДИТОРА ---
async def show_list_in_edit_mode(
    bot: Bot, chat_id: int, user_id: int, state: FSMContext
):
    temp_list = await orm_get_temp_list(user_id)

    if not temp_list:
        await bot.send_message(
            chat_id, "📭 Список порожній.", reply_markup=get_my_list_submenu_kb()
        )
        await state.clear()
        return

    text = "✏️ **Режим редагування**\nНатисніть на товар, щоб змінити кількість:"
    kb = get_editing_kb(temp_list)

    # Надсилаємо нове повідомлення (або редагуємо старе, якщо зберегли ID)
    # Для надійності в гібридному режимі краще надіслати нове
    sent = await bot.send_message(chat_id, text, reply_markup=kb)
    await state.update_data(editor_message_id=sent.message_id)


# --- ХЕНДЛЕРИ ---


# Обробка натискання на товар
@router.callback_query(ListEditingStates.editing_list, F.data.startswith("edit_item:"))
async def edit_item_handler(callback: CallbackQuery, state: FSMContext):
    product_id = int(callback.data.split(":")[1])
    await state.update_data(product_id=product_id)

    async with async_session() as session:
        product = await orm_get_product_by_id(session, product_id)

    await callback.message.edit_text(
        f"📝 Введіть нову кількість для: **{product.назва}**\n(Або надішліть 0 для видалення)",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🔙 Скасувати", callback_data="edit_item:cancel"
                    )
                ]
            ]
        ),
    )
    await state.set_state(ListEditingStates.waiting_for_new_quantity)


# Скасування вводу кількості
@router.callback_query(
    ListEditingStates.waiting_for_new_quantity, F.data == "edit_item:cancel"
)
async def cancel_edit_item(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await state.set_state(ListEditingStates.editing_list)
    # Перемальовуємо список
    await show_list_in_edit_mode(
        bot, callback.message.chat.id, callback.from_user.id, state
    )
    # Видаляємо старе повідомлення про ввід (опціонально)
    try:
        await callback.message.delete()
    except Exception:
        pass


# Обробка введення числа (кількості)
@router.message(ListEditingStates.waiting_for_new_quantity)
async def process_new_quantity(message: Message, state: FSMContext, bot: Bot):
    if not message.text.isdigit():
        await message.answer("⚠️ Введіть число.")
        return

    qty = int(message.text)
    data = await state.get_data()
    product_id = data.get("product_id")
    user_id = message.from_user.id

    # Оновлюємо БД
    if qty > 0:
        await orm_update_temp_list_item_quantity(user_id, product_id, qty)
    else:
        await orm_delete_temp_list_item(user_id, product_id)
        await message.answer("🗑 Товар видалено.")

    # Повертаємось до списку
    await state.set_state(ListEditingStates.editing_list)
    # Видаляємо повідомлення юзера з цифрою (для чистоти)
    try:
        await message.delete()
    except Exception:
        pass

    # Видаляємо старе повідомлення едітора, якщо воно є
    editor_msg_id = data.get("editor_message_id")
    if editor_msg_id:
        try:
            await bot.delete_message(message.chat.id, editor_msg_id)
        except Exception:
            pass

    await show_list_in_edit_mode(bot, message.chat.id, user_id, state)


# ЗАВЕРШЕННЯ РЕДАГУВАННЯ (Натиснули кнопку "Завершити")
@router.callback_query(ListEditingStates.editing_list, F.data == "edit_list:finish")
async def finish_editing(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.delete()
    # ВАЖЛИВО: Повертаємо Reply-клавіатуру
    await callback.message.answer(
        "✅ Редагування завершено.", reply_markup=get_my_list_submenu_kb()
    )
