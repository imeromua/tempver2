# epicservice/handlers/admin/import_handlers.py

import asyncio
import logging
import os
import shutil
from datetime import datetime

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.base import StorageKey
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from config import ADMIN_IDS, DB_NAME, DB_TYPE
from database.orm import (
    orm_get_all_products_sync,
    orm_get_all_users_sync,
    orm_get_users_with_active_lists,
    orm_smart_import,
)
from handlers.admin.core import _show_admin_panel
from keyboards.inline import (
    get_admin_lock_kb,
    get_admin_main_kb,
    get_import_confirm_kb,
    get_notify_confirmation_kb,
    get_user_main_kb,
)
from lexicon.lexicon import LEXICON
from utils.force_save_helper import force_save_user_list
from utils.import_parser import ImportParser

logger = logging.getLogger(__name__)

router = Router()
router.message.filter(F.from_user.id.in_(ADMIN_IDS))
router.callback_query.filter(F.from_user.id.in_(ADMIN_IDS))


class AdminImportStates(StatesGroup):
    waiting_for_import_file = State()
    analyzing_preview = State()  # Стан перегляду прев'ю
    lock_confirmation = State()
    notify_confirmation = State()


def _create_db_backup():
    """Створює локальний бекап файлу БД (тільки для SQLite)."""
    if DB_TYPE == "sqlite" and os.path.exists(DB_NAME):
        backup_dir = "backups"
        os.makedirs(backup_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(backup_dir, f"backup_{timestamp}_{DB_NAME}")
        try:
            shutil.copy2(DB_NAME, backup_path)
            return os.path.basename(backup_path)
        except Exception as e:
            logger.error(f"Backup failed: {e}")
    return None


async def proceed_with_import(
    message: Message, state: FSMContext, bot: Bot, is_after_force_save: bool = False
):
    back_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=LEXICON.BUTTON_BACK_TO_ADMIN_PANEL, callback_data="admin:main"
                )
            ]
        ]
    )
    text = (
        LEXICON.IMPORT_PROMPT
        if not is_after_force_save
        else "Списки збережено. Надішліть файл."
    )

    try:
        await message.edit_text(text, reply_markup=back_kb)
    except Exception:
        await message.answer(text, reply_markup=back_kb)

    await state.set_state(AdminImportStates.waiting_for_import_file)


# --- Handlers: Блокування дій користувачів ---
@router.callback_query(F.data == "admin:import_products")
async def start_import_handler(callback: CallbackQuery, state: FSMContext, bot: Bot):
    active_users = await orm_get_users_with_active_lists()
    if not active_users:
        await proceed_with_import(callback.message, state, bot)
        await callback.answer()
        return
    users_info = "\n".join(
        [
            f"- Користувач `{user_id}` (позицій: {count})"
            for user_id, count in active_users
        ]
    )
    await state.update_data(
        action_to_perform="import", locked_user_ids=[uid for uid, _ in active_users]
    )
    await state.set_state(AdminImportStates.lock_confirmation)
    await callback.message.edit_text(
        LEXICON.ACTIVE_LISTS_BLOCK.format(users_info=users_info),
        reply_markup=get_admin_lock_kb(action="import"),
    )
    await callback.answer("Дію заблоковано", show_alert=True)


@router.callback_query(
    AdminImportStates.lock_confirmation, F.data.startswith("lock:notify:")
)
async def handle_lock_notify(callback: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    for user_id in data.get("locked_user_ids", []):
        try:
            await bot.send_message(user_id, LEXICON.USER_SAVE_LIST_NOTIFICATION)
        except Exception:
            pass
    await callback.answer(LEXICON.NOTIFICATIONS_SENT, show_alert=True)


@router.callback_query(
    AdminImportStates.lock_confirmation, F.data.startswith("lock:force_save:")
)
async def handle_lock_force_save(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await callback.message.edit_text("Почав примусове збереження...")
    data = await state.get_data()
    user_ids, action = data.get("locked_user_ids", []), data.get("action_to_perform")
    results = []
    for user_id in user_ids:
        user_state_key = StorageKey(bot_id=bot.id, chat_id=user_id, user_id=user_id)
        user_state = FSMContext(storage=state.storage, key=user_state_key)
        results.append(await force_save_user_list(user_id, bot, user_state))

    if not all(results):
        await callback.message.edit_text("Помилки примусового збереження.")
        return
    if action == "import":
        await proceed_with_import(
            callback.message, state, bot, is_after_force_save=True
        )


# === ЕТАП 1: ЗАВАНТАЖЕННЯ ТА АНАЛІЗ (ПРЕВ'Ю) ===
@router.message(AdminImportStates.waiting_for_import_file, F.document)
async def analyze_import_file(message: Message, state: FSMContext, bot: Bot):
    if not message.document.file_name.endswith((".xlsx", ".xls", ".ods")):
        await message.answer(LEXICON.IMPORT_WRONG_FORMAT)
        return

    msg = await message.answer(LEXICON.IMPORT_ANALYZING)

    # Зберігаємо файл тимчасово
    temp_file_path = f"temp_import_{message.from_user.id}_{message.document.file_name}"
    try:
        await bot.download(message.document, destination=temp_file_path)

        # Парсимо тільки для прев'ю (не записуємо в БД)
        parser = ImportParser(temp_file_path)
        if not parser.load_file():
            await msg.edit_text(f"❌ Помилка читання файлу: {parser.validation_errors}")
            os.remove(temp_file_path)
            return

        items, errors = parser.parse_data()
        if not items:
            await msg.edit_text(f"❌ Не знайдено товарів!\n\n{errors[:5]}")
            os.remove(temp_file_path)
            return

        # Формуємо текст прев'ю
        preview_lines = []
        for idx, item in enumerate(items[:5], 1):  # Перші 5
            preview_lines.append(
                f"{idx}. `{item['артикул']}` | {item['назва'][:20]}.. | {item['кількість']} шт"
            )

        preview_text = "\n".join(preview_lines)

        # Оновлюємо повідомлення з кнопками "Імпортувати" / "Скасувати"
        await msg.edit_text(
            LEXICON.IMPORT_PREVIEW.format(
                filename=message.document.file_name,
                format="Excel/ODS",
                rows=len(items),
                preview_text=preview_text,
            ),
            reply_markup=get_import_confirm_kb(),
        )

        # Зберігаємо шлях до файлу в стані, щоб використати на наступному кроці
        await state.update_data(temp_file_path=temp_file_path)
        await state.set_state(AdminImportStates.analyzing_preview)

    except Exception as e:
        logger.error(f"Error analyzing file: {e}")
        # --- ВИПРАВЛЕННЯ: Вимикаємо Markdown для повідомлень про помилки ---
        await msg.edit_text(f"❌ Критична помилка: {e}", parse_mode=None)
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)


# === ЕТАП 2: ПІДТВЕРДЖЕННЯ ІМПОРТУ ===
@router.callback_query(AdminImportStates.analyzing_preview, F.data == "import:cancel")
async def cancel_import(callback: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    path = data.get("temp_file_path")
    if path and os.path.exists(path):
        os.remove(path)

    await callback.message.edit_text("❌ Імпорт скасовано.")
    await state.set_state(None)
    await _show_admin_panel(callback, state, bot)


@router.callback_query(AdminImportStates.analyzing_preview, F.data == "import:confirm")
async def confirm_import(callback: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    temp_file_path = data.get("temp_file_path")

    if not temp_file_path or not os.path.exists(temp_file_path):
        await callback.message.edit_text("❌ Файл втрачено. Спробуйте знову.")
        return

    # Показуємо прогрес (фейковий, але приємний)
    await callback.message.edit_text(LEXICON.IMPORT_PROGRESS)

    # 1. Бекап
    backup_name = _create_db_backup() or "Помилка бекапу"

    try:
        # 2. Реальний імпорт
        result = await orm_smart_import(temp_file_path, callback.from_user.id)

        # 3. Результат
        if "error" in result:
            await callback.message.edit_text(
                LEXICON.IMPORT_ERROR.format(error=result["error"])
            )
        else:
            text = LEXICON.IMPORT_RESULT_SUCCESS.format(
                added=result.get("added", 0),
                updated=result.get("updated", 0),
                deactivated=result.get("deactivated", 0),
                reactivated=result.get("reactivated", 0),
                backup_name=backup_name,
            )

            # Додаємо попередження
            if result.get("errors"):
                text += "\n\n⚠️ Є помилки валідації (див. логи)."

            await callback.message.edit_text(text)

            # Питаємо про розсилку
            await state.update_data(import_result=result)
            await callback.message.answer(
                LEXICON.IMPORT_ASK_FOR_NOTIFICATION,
                reply_markup=get_notify_confirmation_kb(),
            )
            await state.set_state(AdminImportStates.notify_confirmation)

    except Exception as e:
        logger.error(f"Critical import error: {e}")
        # --- ВИПРАВЛЕННЯ: Вимикаємо Markdown ---
        await callback.message.edit_text(f"❌ Критична помилка: {e}", parse_mode=None)
    finally:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)


# --- Розсилка сповіщень ---
async def broadcast_import_update(bot: Bot, result: dict):
    loop = asyncio.get_running_loop()
    try:
        user_ids = await loop.run_in_executor(None, orm_get_all_users_sync)
        if not user_ids:
            return

        all_products = await loop.run_in_executor(None, orm_get_all_products_sync)
        total_sum = sum(p.сума_залишку for p in all_products if p.сума_залишку)

        summary_part = LEXICON.USER_IMPORT_NOTIFICATION_SUMMARY.format(
            total_in_db=result.get("total_in_db", 0),
            total_sum=f"{total_sum:,.2f}".replace(",", " "),
        )
        details_part = LEXICON.USER_IMPORT_NOTIFICATION_DETAILS.format(
            added=result.get("added", 0),
            updated=result.get("updated", 0),
            deactivated=result.get("deactivated", 0),
        )
        departments_part = LEXICON.USER_IMPORT_NOTIFICATION_DEPARTMENTS_TITLE
        dep_stats = result.get("department_stats", {})
        sorted_deps = sorted(dep_stats.items())[:20]

        departments_lines = [
            LEXICON.USER_IMPORT_NOTIFICATION_DEPARTMENT_ITEM.format(
                dep_id=dep_id, count=count
            )
            for dep_id, count in sorted_deps
        ]

        message_text = (
            LEXICON.USER_IMPORT_NOTIFICATION_TITLE
            + summary_part
            + "\n"
            + details_part
            + "\n"
            + departments_part
            + "\n".join(departments_lines)
        )

        for user_id in user_ids:
            try:
                kb = get_admin_main_kb() if user_id in ADMIN_IDS else get_user_main_kb()
                await bot.send_message(user_id, message_text, reply_markup=kb)
            except Exception:
                pass
    except Exception as e:
        logger.error("Error broadcast: %s", e)


@router.callback_query(
    AdminImportStates.notify_confirmation, F.data == "notify_confirm:yes"
)
async def handle_notify_yes(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await callback.message.edit_text(LEXICON.BROADCAST_STARTING)
    data = await state.get_data()
    await state.set_state(None)
    if result := data.get("import_result"):
        asyncio.create_task(broadcast_import_update(bot, result))
    await _show_admin_panel(callback, state, bot)


@router.callback_query(
    AdminImportStates.notify_confirmation, F.data == "notify_confirm:no"
)
async def handle_notify_no(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await callback.message.edit_text(LEXICON.BROADCAST_SKIPPED)
    await state.set_state(None)
    await _show_admin_panel(callback, state, bot)
