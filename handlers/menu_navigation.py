# epicservice/handlers/menu_navigation.py

import asyncio
import logging
import os
from datetime import datetime

import pandas as pd
from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import FSInputFile, Message, ReplyKeyboardRemove

# --- Імпорти конфігурації та БД ---
from config import ADMIN_IDS, ARCHIVES_PATH
from database.engine import async_session
from database.orm import (
    orm_clear_temp_list,
    orm_get_all_collected_items_sync,
    orm_get_temp_list,
    orm_get_user_lists_archive,
)
from handlers.admin.archive_handlers import _pack_user_files_to_zip

# --- Імпорти логіки ---
from handlers.admin.import_handlers import proceed_with_import

# ВИПРАВЛЕНО: Імпортуємо тільки те, що є (стан і генератор звіту)
from handlers.admin.report_handlers import AdminReportStates, _create_stock_report_sync
from handlers.user.list_editing import ListEditingStates, show_list_in_edit_mode
from keyboards.inline import get_confirmation_kb

# --- Імпорти клавіатур ---
from keyboards.reply import (
    BTN_ADMIN_PANEL,
    BTN_ALL_ARCHIVES,
    BTN_BACK,
    BTN_DELETE_ALL_ARCHIVES,
    BTN_DELETE_LIST,
    BTN_DOWNLOAD_ALL,
    BTN_EDIT_LIST,
    BTN_EXPORT_COLLECTED,
    BTN_EXPORT_STOCK,
    BTN_IMPORT,
    BTN_IMPORT_COLLECTED,
    BTN_MY_ARCHIVES,
    BTN_MY_LIST,
    BTN_NEW_LIST,
    BTN_SAVE_LIST,
    BTN_TO_MAIN_MENU,
    BTN_USERS,
    BTN_UTIL_BROADCAST,
    BTN_UTIL_CLEAN_DB,
    BTN_UTIL_CONVERTER,
    BTN_UTIL_VALIDATOR,
    BTN_UTILITIES,
    get_admin_menu_kb,
    get_archives_submenu_kb,
    get_main_menu_kb,
    get_my_list_submenu_kb,
    get_utilities_menu_kb,
)
from utils.list_processor import process_and_save_list

logger = logging.getLogger(__name__)
router = Router()

# ==============================================================================
# 🚪 ВХІД В МЕНЮ (Адмінка та Головне)
# ==============================================================================


@router.message(F.text == BTN_ADMIN_PANEL)
async def open_admin_panel(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    await message.answer(
        "👑 **Панель адміністратора**", reply_markup=get_admin_menu_kb()
    )


@router.message(F.text == BTN_TO_MAIN_MENU)
async def exit_admin_panel(message: Message):
    is_admin = message.from_user.id in ADMIN_IDS
    await message.answer("🔙 Головне меню:", reply_markup=get_main_menu_kb(is_admin))


# ==============================================================================
# 👤 КОРИСТУВАЧ: ГОЛОВНЕ МЕНЮ
# ==============================================================================


@router.message(F.text == BTN_MY_LIST)
async def open_my_list_menu(message: Message):
    user_id = message.from_user.id
    temp_list = await orm_get_temp_list(user_id)

    if not temp_list:
        await message.answer(
            "📭 Ваш список наразі порожній.", reply_markup=get_my_list_submenu_kb()
        )
        return

    dept = temp_list[0].product.відділ
    text_lines = [f"📋 **Ваш список (Відділ: {dept}):**\n"]

    total_qty = 0
    for item in temp_list:
        total_qty += item.quantity
        text_lines.append(
            f"• `{item.product.артикул}` {item.product.назва} — **{item.quantity}**"
        )

    text_lines.append(f"\n🔹 Всього позицій: {len(temp_list)}")
    text_lines.append(f"🔹 Сума одиниць: {total_qty}")

    full_text = "\n".join(text_lines)
    if len(full_text) > 4000:
        full_text = full_text[:4000] + "\n... (список занадто довгий)"

    await message.answer(full_text, reply_markup=get_my_list_submenu_kb())


@router.message(F.text == BTN_MY_ARCHIVES)
async def open_my_archives_menu(message: Message):
    user_id = message.from_user.id
    archives = await orm_get_user_lists_archive(user_id)

    count = len(archives)
    if count == 0:
        text = "🗂 У вас немає збережених списків в архіві."
    else:
        last_date = archives[0].created_at.strftime("%d.%m.%Y")
        text = (
            f"🗂 Всього збережених списків: **{count}**.\n"
            f"Останній від: {last_date}\n"
            f"Ви можете завантажити їх усі одним архівом."
        )

    await message.answer(text, reply_markup=get_archives_submenu_kb())


@router.message(F.text == BTN_NEW_LIST)
async def create_new_list(message: Message):
    await orm_clear_temp_list(message.from_user.id)
    is_admin = message.from_user.id in ADMIN_IDS
    await message.answer(
        "✅ Список очищено. Можете починати новий збір!",
        reply_markup=get_main_menu_kb(is_admin),
    )


# ==============================================================================
# 📋 КОРИСТУВАЧ: ПІДМЕНЮ "МІЙ СПИСОК"
# ==============================================================================


@router.message(F.text == BTN_BACK)
async def go_back_logic(message: Message, state: FSMContext):
    user_id = message.from_user.id
    is_admin = user_id in ADMIN_IDS
    await state.clear()

    if is_admin:
        await message.answer("🔙 Повернення:", reply_markup=get_admin_menu_kb())
    else:
        await message.answer("🔙 Головне меню:", reply_markup=get_main_menu_kb(False))


@router.message(F.text == BTN_DELETE_LIST)
async def delete_current_list(message: Message):
    await orm_clear_temp_list(message.from_user.id)
    is_admin = message.from_user.id in ADMIN_IDS
    await message.answer(
        "🗑 Поточний список видалено.", reply_markup=get_main_menu_kb(is_admin)
    )


@router.message(F.text == BTN_SAVE_LIST)
async def save_current_list_trigger(message: Message, state: FSMContext, bot: Bot):
    user_id = message.from_user.id
    msg = await message.answer("⏳ Зберігаю список...")

    main_list_path = None
    surplus_list_path = None

    try:
        async with async_session() as session:
            async with session.begin():
                main_list_path, surplus_list_path = await process_and_save_list(
                    session, user_id
                )

        await msg.delete()

        if not main_list_path and not surplus_list_path:
            await message.answer("❌ Список порожній або виникла помилка.")
        else:
            if main_list_path:
                await bot.send_document(
                    user_id, FSInputFile(main_list_path), caption="✅ Ваше замовлення"
                )
                if os.path.exists(main_list_path):
                    os.remove(main_list_path)
            if surplus_list_path:
                await bot.send_document(
                    user_id, FSInputFile(surplus_list_path), caption="⚠️ Лишки (дефіцит)"
                )
                if os.path.exists(surplus_list_path):
                    os.remove(surplus_list_path)

            is_admin = user_id in ADMIN_IDS
            await message.answer(
                "✅ Список збережено та очищено!",
                reply_markup=get_main_menu_kb(is_admin),
            )

    except Exception as e:
        logger.error(f"Save list error: {e}")
        await message.answer("❌ Помилка збереження.")


# У файлі menu_navigation.py


@router.message(F.text == BTN_EDIT_LIST)
async def edit_list_trigger(message: Message, state: FSMContext, bot: Bot):
    await state.set_state(ListEditingStates.editing_list)
    # Reply клавіатуру не ховаємо (Remove), нехай висить.
    # Але Inline меню з'явиться новим повідомленням.
    await show_list_in_edit_mode(bot, message.chat.id, message.from_user.id, state)


# ==============================================================================
# 🗂 КОРИСТУВАЧ: ПІДМЕНЮ "МОЇ АРХІВИ"
# ==============================================================================


@router.message(F.text == BTN_DOWNLOAD_ALL)
async def download_all_archives(message: Message):
    msg = await message.answer("⏳ Пакую всі ваші файли в архів...")
    zip_path = await _pack_user_files_to_zip(message.from_user.id)

    if zip_path:
        await message.answer_document(
            FSInputFile(zip_path), caption="📦 Ваша повна історія списків"
        )
        await msg.delete()
        if os.path.exists(zip_path):
            os.remove(zip_path)
    else:
        await msg.edit_text("❌ Архів порожній або сталася помилка.")


@router.message(F.text == BTN_DELETE_ALL_ARCHIVES)
async def delete_all_archives_trigger(message: Message, state: FSMContext):
    await message.answer(
        "⚠️ **Ви точно хочете видалити ВСЮ історію?**\nЦю дію неможливо скасувати.",
        reply_markup=get_confirmation_kb(
            "archive:delete_all:yes", "archive:delete_all:no"
        ),
    )


# ==============================================================================
# 👑 АДМІНКА: ДІЇ
# ==============================================================================


@router.message(F.text == BTN_IMPORT)
async def admin_import_trigger(message: Message, state: FSMContext, bot: Bot):
    await proceed_with_import(message, state, bot)


@router.message(F.text == BTN_EXPORT_STOCK)
async def admin_export_stock(message: Message, state: FSMContext, bot: Bot):
    await message.answer("📤 Експортую залишки...")

    loop = asyncio.get_running_loop()
    # Використовуємо функцію прямо з report_handlers
    report_path = await loop.run_in_executor(None, _create_stock_report_sync)

    if report_path:
        await message.answer_document(
            FSInputFile(report_path), caption="📊 Звіт по залишках"
        )
        if os.path.exists(report_path):
            os.remove(report_path)
    else:
        await message.answer("❌ Помилка створення звіту.")


@router.message(F.text == BTN_EXPORT_COLLECTED)
async def admin_export_collected(message: Message):
    await message.answer("📋 Формую звіт по зібраному...")

    loop = asyncio.get_running_loop()
    items = await loop.run_in_executor(None, orm_get_all_collected_items_sync)

    if not items:
        await message.answer("📭 Зібраних товарів ще немає.")
        return

    df = pd.DataFrame(items)
    # Ренейм для краси
    df.rename(
        columns={
            "name": "Назва",
            "quantity": "Кількість",
            "department": "Відділ",
            "group": "Група",
        },
        inplace=True,
    )

    filename = f"collected_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
    path = os.path.join(ARCHIVES_PATH, filename)
    os.makedirs(ARCHIVES_PATH, exist_ok=True)

    await loop.run_in_executor(None, lambda: df.to_excel(path, index=False))

    await message.answer_document(FSInputFile(path), caption="📋 Зібрані товари")
    if os.path.exists(path):
        os.remove(path)


@router.message(F.text == BTN_IMPORT_COLLECTED)
async def admin_import_collected_trigger(message: Message, state: FSMContext):
    await message.answer(
        "📉 **Імпорт зібраного (віднімання)**\n"
        "Надішліть Excel-файл з колонками `Артикул` та `Кількість`.\n"
        "Це відніме вказану кількість від залишків складу.",
        reply_markup=ReplyKeyboardRemove(),
    )
    await state.set_state(AdminReportStates.waiting_for_subtract_file)
    await state.update_data(main_message_id=message.message_id)


@router.message(F.text == BTN_USERS)
async def admin_users_placeholder(message: Message):
    await message.answer(
        "👥 Розділ 'Користувачі' в розробці.\nТут буде список юзерів і бани."
    )


@router.message(F.text == BTN_ALL_ARCHIVES)
async def admin_all_archives_placeholder(message: Message):
    await message.answer("🗄 Розділ 'Архіви всіх' в розробці.")


# ==============================================================================
# 🛠 АДМІНКА: УТИЛІТИ
# ==============================================================================


@router.message(F.text == BTN_UTILITIES)
async def open_utilities(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    await message.answer(
        "🛠 **Утиліти та Інструменти**", reply_markup=get_utilities_menu_kb()
    )


@router.message(F.text == BTN_UTIL_BROADCAST)
async def util_broadcast_trigger(message: Message, state: FSMContext):
    # Тут потрібен імпорт із utilities.py, але щоб уникнути циклічних імпортів,
    # краще ловити текст прямо в utilities.py.
    # Оскільки цей хендлер вже є в utilities.py, тут ми просто даємо йому спрацювати.
    # (Цей блок можна видалити, бо utilities.py сам зловить цей текст, якщо він підключений в bot.py)
    # Але для надійності я залишив в utilities.py обробник message(F.text == "📢 Розсилка").
    pass


@router.message(F.text == BTN_UTIL_VALIDATOR)
async def util_validator_trigger(message: Message):
    pass


@router.message(F.text == BTN_UTIL_CONVERTER)
async def util_converter_trigger(message: Message):
    pass


@router.message(F.text == BTN_UTIL_CLEAN_DB)
async def util_clean_db_trigger(message: Message):
    # А ось тут ми можемо викликати підтвердження
    await message.answer(
        "🧨 **ПОВНА ОЧИСТКА БД**\n\n"
        "Ви збираєтесь видалити:\n"
        "- Всі товари\n- Всі списки користувачів\n- Всю історію\n\n"
        "Ви впевнені?",
        reply_markup=get_confirmation_kb("clean_db:yes", "clean_db:no"),
    )
