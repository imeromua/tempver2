# epicservice/handlers/admin/backup_handlers.py

import logging
import os

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, FSInputFile

from config import ADMIN_IDS, BACKUP_DIR
from keyboards.inline import get_backups_menu_kb
from lexicon.lexicon import LEXICON
from utils.backup_utils import create_backup, delete_old_backups, get_backups_list

# --- ДОДАНО: Імпортуємо наш коректор ---
from utils.markdown_corrector import escape_markdown

logger = logging.getLogger(__name__)
router = Router()
router.callback_query.filter(F.from_user.id.in_(ADMIN_IDS))


@router.callback_query(F.data == "admin:backups_menu")
async def open_backups_menu(callback: CallbackQuery):
    backups = get_backups_list()

    text = LEXICON.BACKUPS_TITLE + "\n\n"
    if not backups:
        text += LEXICON.BACKUP_NO_FILES
    else:
        for b in backups[:5]:
            # Екрануємо назву файлу, бо в ній є підкреслення "_"
            safe_filename = escape_markdown(b["filename"])

            text += (
                LEXICON.BACKUP_ITEM_TEMPLATE.format(
                    filename=safe_filename,
                    date=b["date"],
                    size=b["size"],
                    type=b["type"],
                )
                + "\n\n"
            )

    try:
        await callback.message.edit_text(
            text, reply_markup=get_backups_menu_kb(backups)
        )
    except TelegramBadRequest:
        await callback.answer()


@router.callback_query(F.data == "backup:create")
async def handle_create_backup(callback: CallbackQuery):
    filename = create_backup(prefix="manual")
    if filename:
        await callback.answer("Бекап створено!", show_alert=True)
        await open_backups_menu(callback)
    else:
        await callback.answer("Помилка створення бекапу.", show_alert=True)


@router.callback_query(F.data == "backup:cleanup")
async def handle_cleanup_backups(callback: CallbackQuery):
    count = delete_old_backups(keep_last=5)
    await callback.answer(
        LEXICON.BACKUP_DELETED_COUNT.format(count=count), show_alert=True
    )
    await open_backups_menu(callback)


@router.callback_query(F.data.startswith("backup:download:"))
async def handle_download_backup(callback: CallbackQuery):
    filename = callback.data.split(":")[-1]
    path = os.path.join(BACKUP_DIR, filename)

    if os.path.exists(path):
        # Екрануємо назву файлу для підпису
        safe_filename = escape_markdown(filename)

        await callback.message.answer_document(
            FSInputFile(path),
            caption=f"💾 Бекап: `{safe_filename}`",  # Тепер можна використовувати Markdown!
        )
        await callback.answer()
    else:
        await callback.answer("Файл не знайдено!", show_alert=True)
