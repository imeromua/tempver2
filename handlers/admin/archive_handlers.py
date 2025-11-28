# epicservice/handlers/admin/archive_handlers.py

import logging

from aiogram import F, Router
from aiogram.types import Message

from config import ADMIN_IDS
from database.orm import orm_get_all_archives

logger = logging.getLogger(__name__)
router = Router()


# ==============================================================================
# 🗄 АДМІН: ПЕРЕГЛЯД АРХІВІВ ВСІХ КОРИСТУВАЧІВ
# ==============================================================================


@router.message(F.text == "🗄 Архіви всіх")
async def admin_view_all_archives(message: Message):
    """Показує статистику по всіх архівах (для адміна)."""
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("🚫 У вас немає доступу до цієї функції.")
        return

    archives = await orm_get_all_archives()

    if not archives:
        await message.answer("📭 Архіви відсутні.")
        return

    # Групуємо архіви по користувачах
    user_archives = {}
    for archive in archives:
        user_id = archive.user_id
        if user_id not in user_archives:
            user_archives[user_id] = []
        user_archives[user_id].append(archive)

    # Формуємо статистику
    text_lines = [f"🗄 **Архіви всіх користувачів:**\n"]

    for user_id, user_lists in sorted(
        user_archives.items(), key=lambda x: len(x[1]), reverse=True
    ):
        count = len(user_lists)
        last_date = user_lists[0].created_at.strftime("%d.%m.%Y")
        text_lines.append(
            f"• User ID: `{user_id}` — {count} списків (останній: {last_date})"
        )

    text_lines.append(f"\n📊 Всього користувачів: **{len(user_archives)}**")
    text_lines.append(f"📊 Всього списків: **{len(archives)}**")

    full_text = "\n".join(text_lines)
    if len(full_text) > 4000:
        full_text = full_text[:3900] + "\n... (список обрізано)"

    await message.answer(full_text)


# Це внутрішні функції, які використовуються в menu_navigation.py
# Перенесені сюди для зручності


async def _pack_user_files_to_zip(user_id: int):
    """
    Внутрішня функція для пакування файлів користувача в ZIP.
    Використовується в menu_navigation.py
    """
    from database.orm import orm_pack_user_files_to_zip

    return await orm_pack_user_files_to_zip(user_id)


async def _delete_user_archives(user_id: int):
    """
    Внутрішня функція для видалення архівів користувача.
    Використовується в menu_navigation.py
    """
    from database.orm import orm_delete_user_archives

    return await orm_delete_user_archives(user_id)
